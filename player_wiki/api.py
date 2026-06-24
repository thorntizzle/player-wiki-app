from __future__ import annotations

import base64
import binascii
from collections import defaultdict
from functools import wraps
import hashlib
from io import BytesIO
from pathlib import Path
import re
from datetime import timedelta
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request, send_file, url_for

from .admin_audit import (
    build_activity_params,
    build_activity_query_url,
    get_activity_filters,
    list_audit_event_type_choices,
    load_dashboard_audit_context,
    load_user_audit_context,
)
from .admin_context import (
    build_campaign_lookup,
    build_user_card_summaries,
    build_user_reference_payload,
    get_assignment_form_defaults,
    get_invite_form_defaults,
    get_membership_form_defaults,
    list_campaign_choices,
    list_character_choices,
)
from .auth import (
    can_access_campaign_scope,
    can_access_campaign_systems_entry,
    can_access_campaign_systems_source,
    can_manage_campaign_combat,
    can_manage_campaign_content,
    can_manage_campaign_dm_content,
    can_manage_campaign_visibility,
    can_manage_campaign_session,
    can_manage_campaign_systems,
    can_post_campaign_session_messages,
    clear_campaign_visibility_cache,
    get_accessible_campaign_entries,
    get_auth_store,
    get_campaign_default_scope_visibility,
    get_campaign_role,
    get_campaign_scope_visibility,
    get_current_auth_source,
    get_current_user_preferences,
    get_current_memberships,
    get_current_user,
    get_effective_campaign_visibility,
    get_public_campaign_entries,
    get_repository,
    has_session_mode_access,
)
from .auth_store import (
    SESSION_CHAT_ORDER_CHOICES,
    is_valid_session_chat_order,
    normalize_frontend_mode,
    normalize_session_chat_order,
    isoformat,
)
from .campaign_combat_service import CampaignCombatRevisionConflictError, CampaignCombatValidationError
from .campaign_content_service import (
    CampaignContentError,
    delete_campaign_asset_file,
    delete_campaign_character_file,
    delete_campaign_page_file,
    get_campaign_asset_file_record,
    get_campaign_character_file,
    get_campaign_config_file,
    get_campaign_page_file,
    guess_campaign_asset_media_type,
    list_campaign_asset_files,
    list_campaign_character_files,
    list_campaign_page_files,
    update_campaign_config_file,
    write_campaign_asset_file,
    write_campaign_character_file,
    write_campaign_page_file,
)
from .campaign_dm_content_service import (
    CampaignDMContentValidationError,
    build_statblock_parser_feedback,
)
from .campaign_wiki_safety import build_dm_player_wiki_removal_safety_index
from .campaign_session_service import (
    ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS,
    CampaignSessionValidationError,
)
from .campaign_visibility import (
    CAMPAIGN_VISIBILITY_SCOPES,
    CAMPAIGN_VISIBILITY_SCOPE_LABELS,
    VISIBILITY_LABELS,
    VISIBILITY_PRIVATE,
    is_valid_visibility,
    list_visibility_choices,
    normalize_visibility_choice,
)
from .character_builder import (
    CAMPAIGN_ITEMS_SECTION,
    CAMPAIGN_MECHANICS_SECTION,
    _attach_campaign_item_page_support,
    _build_item_catalog,
    _build_spell_catalog,
    _list_campaign_enabled_entries,
    _normalize_equipment_payloads,
    _normalize_weapon_wield_mode_value,
    CharacterBuildError,
    apply_imported_progression_repairs,
    build_imported_progression_repair_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    build_native_level_up_character_definition,
    build_native_level_up_context,
    describe_equipment_state_support,
    native_level_up_readiness,
    normalize_definition_to_native_model,
    resolve_weapon_wield_mode,
    weapon_wield_mode_label,
)
from .character_page_records import (
    list_builder_campaign_page_records as list_builder_campaign_page_records_for_store,
    list_visible_character_page_records as list_visible_character_page_records_for_store,
)
from .character_editor import (
    CharacterEditValidationError,
    apply_native_character_retraining,
    apply_native_character_edits,
    apply_equipment_state_edit,
    build_linked_feature_authoring_support,
    build_managed_character_import_metadata,
    build_native_character_edit_context,
    build_native_character_retraining_context,
)
from .character_importer import write_yaml
from .character_models import CharacterRecord, CharacterStateRecord
from .character_profile import profile_class_level_text
from .character_presenter import (
    build_character_entry_href,
    build_character_inventory_item_ref,
    present_arcane_armor_state,
    present_character_detail,
    present_character_roster,
    resolve_item_description_html,
)
from .themes import get_theme_preset, is_valid_theme_key, list_theme_presets
from .character_service import CharacterStateValidationError, build_initial_state, merge_state_with_definition
from .character_store import CharacterStateConflictError
from .character_repository import load_campaign_character_config
from .combat_presenter import DND_5E_CONDITION_OPTIONS, present_combat_tracker
from .models import section_sort_key, subsection_sort_key
from .player_choices import build_active_player_choices
from .repository import slugify
from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
    parse_session_article_source_ref,
)
from .session_article_publisher import list_published_pages_for_session_articles
from .session_presenter import present_session_dm_passive_score_rows
from .session_source_presenter import (
    build_session_article_source_search_results as build_shared_session_article_source_search_results,
)
from .systems_importer import Dnd5eSystemsImporter, SUPPORTED_ENTRY_TYPES
from .systems_ingest import SystemsIngestError, extracted_systems_archive
from .systems_labels import (
    SYSTEMS_ENTRY_TYPE_LABELS,
    SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
    systems_entry_type_label,
    systems_entry_type_choice_labels,
    systems_entry_type_sort_key,
)
from .systems_service import LICENSE_CLASS_LABELS, SystemsPolicyValidationError
from .system_policy import (
    CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP,
    CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION,
    CHARACTER_ROUTE_LANE_DND5E,
    CHARACTER_ROUTE_LANE_XIANXIA,
    character_advancement_lane,
    character_advancement_unsupported_message,
    native_character_create_lane,
    native_character_create_unsupported_message,
    supports_character_controls_routes,
    supports_combat_tracker,
    supports_dnd5e_systems_import,
    supports_native_character_create,
    supports_native_character_tools,
    is_dnd_5e_system,
    is_xianxia_system,
)
from .version import build_app_metadata
from .xianxia_advancement import (
    advance_xianxia_martial_art_rank_definition,
    apply_xianxia_divine_realm_rebuild_definition,
    apply_xianxia_immortal_realm_rebuild_definition,
    confirm_xianxia_realm_ascension_definition,
    learn_xianxia_generic_technique_definition,
    list_xianxia_generic_technique_learning_options,
    record_xianxia_dao_immolating_use_definition,
    request_xianxia_dao_immolating_use_definition,
    reset_xianxia_realm_ascension_stats_definition,
    spend_xianxia_conditioning_definition,
    spend_xianxia_cultivation_energy_definition,
    spend_xianxia_meditation_definition,
    spend_xianxia_training_definition,
    start_xianxia_realm_ascension_review_definition,
)
from . import xianxia_cultivation
from .xianxia_character_builder import (
    XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT,
    XIANXIA_MARTIAL_ART_IMPORT_RANKS,
    build_xianxia_character_create_context,
    build_xianxia_character_definition,
    build_xianxia_character_initial_state,
    list_xianxia_manual_import_martial_art_options,
)
from .xianxia_character_importer import build_xianxia_manual_import_character
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    XIANXIA_ENERGY_KEYS,
)


CHARACTER_PORTRAIT_ALT_MAX_LENGTH = 200
CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH = 300
CHARACTER_PORTRAIT_MAX_BYTES = 8 * 1024 * 1024


def register_api(app) -> None:
    api = Blueprint("api", __name__, url_prefix="/api/v1")

    def json_error(
        message: str,
        status_code: int,
        *,
        code: str = "error",
        details: dict[str, Any] | None = None,
    ):
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if details:
            payload["error"]["details"] = details
        return jsonify(payload), status_code

    def serialize_datetime(value) -> str | None:
        if value is None:
            return None
        return isoformat(value)

    def load_json_object() -> dict[str, Any]:
        if not request.data:
            return {}
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def decode_embedded_file(
        payload: object,
        *,
        label: str,
        require_media_type: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError(f"{label} must be an object.")

        filename = str(payload.get("filename") or "").strip()
        data_base64 = str(payload.get("data_base64") or "").strip()
        media_type = str(payload.get("media_type") or "").strip() or None
        if not filename:
            raise ValueError(f"{label} filename is required.")
        if require_media_type and not media_type:
            raise ValueError(f"{label} media_type is required.")
        if not data_base64:
            raise ValueError(f"{label} data_base64 is required.")

        try:
            data_blob = base64.b64decode(data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"{label} data_base64 must be valid base64.") from exc

        return {
            "filename": filename,
            "media_type": media_type,
            "data_blob": data_blob,
        }

    def api_login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return view(*args, **kwargs)

        return wrapped

    def api_admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if user is None:
                return json_error("Authentication required.", 401, code="auth_required")
            if not user.is_admin:
                return json_error("You do not have permission to use the admin API.", 403, code="forbidden")
            return view(*args, **kwargs)

        return wrapped

    def api_campaign_scope_access_required(scope: str):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                campaign_slug = kwargs.get("campaign_slug")
                if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                    abort(404)

                if can_access_campaign_scope(campaign_slug, scope):
                    return view(*args, **kwargs)

                if get_current_user() is None:
                    return json_error("Authentication required.", 401, code="auth_required")
                return json_error("You do not have access to this campaign scope.", 403, code="forbidden")

            return wrapped

        return decorator

    def api_campaign_content_management_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            campaign_slug = kwargs.get("campaign_slug")
            if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                abort(404)

            if can_manage_campaign_content(campaign_slug):
                return view(*args, **kwargs)

            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have permission to manage campaign content.", 403, code="forbidden")

        return wrapped

    def api_campaign_systems_management_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            campaign_slug = kwargs.get("campaign_slug")
            if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                abort(404)

            if can_manage_campaign_systems(campaign_slug):
                return view(*args, **kwargs)

            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have permission to manage systems.", 403, code="forbidden")

        return wrapped

    def api_campaign_visibility_management_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            campaign_slug = kwargs.get("campaign_slug")
            if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                abort(404)

            if can_manage_campaign_visibility(campaign_slug):
                return view(*args, **kwargs)

            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have permission to manage campaign visibility.", 403, code="forbidden")

        return wrapped

    def api_campaign_systems_source_access_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            campaign_slug = kwargs.get("campaign_slug")
            source_id = kwargs.get("source_id")
            if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                abort(404)
            if not isinstance(source_id, str):
                abort(404)

            if can_access_campaign_systems_source(campaign_slug, source_id):
                return view(*args, **kwargs)

            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have access to this systems source.", 403, code="forbidden")

        return wrapped

    def api_campaign_systems_entry_access_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            campaign_slug = kwargs.get("campaign_slug")
            entry_slug = kwargs.get("entry_slug")
            if not isinstance(campaign_slug, str) or get_repository().get_campaign(campaign_slug) is None:
                abort(404)
            if not isinstance(entry_slug, str):
                abort(404)

            if can_access_campaign_systems_entry(campaign_slug, entry_slug):
                return view(*args, **kwargs)

            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have access to this systems entry.", 403, code="forbidden")

        return wrapped

    def coerce_bool(value: object, *, label: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        normalized = str(value or "").strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{label} must be true or false.")

    def serialize_user(user) -> dict[str, Any]:
        return {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
            "status": user.status,
            "created_at": serialize_datetime(user.created_at),
            "updated_at": serialize_datetime(user.updated_at),
        }

    def serialize_membership(membership) -> dict[str, Any]:
        return {
            "id": membership.id,
            "campaign_slug": membership.campaign_slug,
            "role": membership.role,
            "status": membership.status,
            "created_at": serialize_datetime(membership.created_at),
            "updated_at": serialize_datetime(membership.updated_at),
        }

    def serialize_campaign(campaign) -> dict[str, Any]:
        return {
            "slug": campaign.slug,
            "title": campaign.title,
            "summary": campaign.summary,
            "system": campaign.system,
            "current_session": campaign.current_session,
            "systems_library_slug": campaign.systems_library_slug,
        }

    def serialize_campaign_entry(entry) -> dict[str, Any]:
        return {
            "campaign": serialize_campaign(entry.campaign),
            "role": entry.role,
        }

    def build_admin_local_url(path: str) -> str:
        return f"{current_app.config['BASE_URL'].rstrip('/')}{path}"

    def build_admin_user_reference(
        user_id: int | None,
        display_name: str | None,
        email: str | None,
    ) -> dict[str, str] | None:
        if user_id is None or email is None:
            return None
        return build_user_reference_payload(
            user_id,
            display_name,
            email,
            href=f"/app-next/admin/users/{user_id}",
            flask_href=url_for("admin_user_detail", user_id=user_id),
        )

    def serialize_admin_membership(membership, campaign_lookup: dict[str, str]) -> dict[str, Any]:
        payload = serialize_membership(membership)
        payload["campaign_title"] = campaign_lookup.get(membership.campaign_slug, membership.campaign_slug)
        return payload

    def serialize_admin_assignment(assignment, campaign_lookup: dict[str, str]) -> dict[str, Any]:
        return {
            "id": assignment.id,
            "user_id": assignment.user_id,
            "campaign_slug": assignment.campaign_slug,
            "campaign_title": campaign_lookup.get(assignment.campaign_slug, assignment.campaign_slug),
            "character_slug": assignment.character_slug,
            "assignment_type": assignment.assignment_type,
            "created_at": serialize_datetime(assignment.created_at),
            "updated_at": serialize_datetime(assignment.updated_at),
        }

    def build_admin_dashboard_context() -> dict[str, Any]:
        store = get_auth_store()
        repository = get_repository()
        users = store.list_users()
        campaign_choices = list_campaign_choices(repository)
        campaign_lookup = build_campaign_lookup(repository)

        dashboard_audit_context = load_dashboard_audit_context(
            store,
            campaign_lookup,
            get_activity_filters(request.args, campaign_choices),
            build_page_url=lambda filters, page: build_activity_query_url("/app-next/admin", filters, page=page),
            build_export_url=lambda filters: url_for(
                "admin_activity_export",
                **build_activity_params(filters, page=1),
            ),
            build_user_reference=build_admin_user_reference,
            include_event_id=True,
        )

        current_user = get_current_user()
        return {
            "ok": True,
            "admin_user": serialize_user(current_user) if current_user is not None else None,
            "campaign_choices": campaign_choices,
            "invite_form_defaults": get_invite_form_defaults(campaign_choices),
            "audit_event_type_choices": list_audit_event_type_choices(),
            "user_cards": build_user_card_summaries(
                store,
                users,
                campaign_lookup,
                build_links=lambda user: {
                    "href": f"/app-next/admin/users/{user.id}",
                    "flask_href": url_for("admin_user_detail", user_id=user.id),
                },
            ),
            "links": {
                "gen2_admin_url": "/app-next/admin",
                "flask_admin_url": url_for("admin_dashboard"),
            },
            **dashboard_audit_context,
        }

    def require_admin_target_user(user_id: int):
        user = get_auth_store().get_user_by_id(user_id)
        if user is None:
            abort(404)
        return user

    def build_admin_user_detail_context(user) -> dict[str, Any]:
        store = get_auth_store()
        repository = get_repository()
        campaigns = list_campaign_choices(repository)
        character_choices = list_character_choices(repository, get_character_repository())
        campaign_lookup = build_campaign_lookup(repository)
        memberships = store.list_memberships_for_user(
            user.id,
            statuses=("active", "invited", "removed"),
        )
        assignments = store.list_character_assignments_for_user(user.id)
        current_user = get_current_user()
        user_audit_context = load_user_audit_context(
            store,
            campaign_lookup,
            get_activity_filters(request.args, campaigns),
            user_id=user.id,
            build_page_url=lambda filters, page: build_activity_query_url(
                f"/app-next/admin/users/{user.id}",
                filters,
                page=page,
            ),
            build_export_url=lambda filters: url_for(
                "admin_user_activity_export",
                user_id=user.id,
                **build_activity_params(filters, page=1),
            ),
            build_user_reference=build_admin_user_reference,
            include_event_id=True,
        )

        return {
            "ok": True,
            "managed_user": serialize_user(user),
            "campaign_choices": campaigns,
            "character_choices": character_choices,
            "memberships": [serialize_admin_membership(membership, campaign_lookup) for membership in memberships],
            "assignments": [serialize_admin_assignment(assignment, campaign_lookup) for assignment in assignments],
            "audit_event_type_choices": list_audit_event_type_choices(),
            "membership_form_defaults": get_membership_form_defaults(request.args, store, user.id, campaigns),
            "assignment_form_defaults": get_assignment_form_defaults(request.args, character_choices),
            "can_manage_account": current_user is not None and current_user.id != user.id,
            "links": {
                "gen2_admin_url": "/app-next/admin",
                "flask_admin_url": url_for("admin_dashboard"),
                "gen2_user_url": f"/app-next/admin/users/{user.id}",
                "flask_user_url": url_for("admin_user_detail", user_id=user.id),
            },
            **user_audit_context,
        }

    def serialize_campaign_help_link(link: object) -> dict[str, str]:
        source = link if isinstance(link, dict) else {}
        return {
            "label": str(source.get("label") or "").strip(),
            "href": str(source.get("href") or "").strip(),
        }

    def serialize_campaign_help_guidance_card(card: object) -> dict[str, Any]:
        source = card if isinstance(card, dict) else {}
        items = source.get("items")
        return {
            "title": str(source.get("title") or "").strip(),
            "body": str(source.get("body") or "").strip(),
            "items": [str(item).strip() for item in items if str(item).strip()] if isinstance(items, list) else [],
            "meta": str(source.get("meta") or "").strip(),
        }

    def serialize_campaign_help_surface(surface: object) -> dict[str, Any]:
        source = surface if isinstance(surface, dict) else {}
        capabilities = source.get("capabilities")
        limits = source.get("limits")
        links = source.get("links")
        guidance_cards = source.get("guidance_cards")
        return {
            "anchor": str(source.get("anchor") or "").strip(),
            "label": str(source.get("label") or "").strip(),
            "summary": str(source.get("summary") or "").strip(),
            "status_label": str(source.get("status_label") or "").strip(),
            "access_note": str(source.get("access_note") or "").strip(),
            "capabilities": [str(item).strip() for item in capabilities if str(item).strip()]
            if isinstance(capabilities, list)
            else [],
            "limits": [str(item).strip() for item in limits if str(item).strip()]
            if isinstance(limits, list)
            else [],
            "links": [serialize_campaign_help_link(link) for link in links] if isinstance(links, list) else [],
            "guidance_cards": [
                serialize_campaign_help_guidance_card(card)
                for card in guidance_cards
            ]
            if isinstance(guidance_cards, list)
            else [],
        }

    def serialize_campaign_help_visibility_row(row: object) -> dict[str, Any]:
        source = row if isinstance(row, dict) else {}
        return {
            "label": str(source.get("label") or "").strip(),
            "visibility_label": str(source.get("visibility_label") or "").strip(),
            "viewer_can_open": bool(source.get("viewer_can_open")),
        }

    def serialize_page(page) -> dict[str, Any]:
        return {
            "title": page.title,
            "route_slug": page.route_slug,
            "section": page.section,
            "subsection": page.subsection,
            "page_type": page.page_type,
            "display_order": page.display_order,
            "published": page.published,
            "aliases": list(page.aliases),
            "summary": page.summary,
            "image_path": page.image_path,
            "image_alt": page.image_alt,
            "image_caption": page.image_caption,
            "reveal_after_session": page.reveal_after_session,
            "source_ref": page.source_ref,
            "is_pinned": page.is_pinned,
        }

    def flask_campaign_href(campaign_slug: str, suffix: str = "") -> str:
        suffix = suffix.strip("/")
        if suffix:
            return f"/campaigns/{campaign_slug}/{suffix}"
        return f"/campaigns/{campaign_slug}"

    def gen2_campaign_href(campaign_slug: str, suffix: str = "") -> str:
        suffix = suffix.strip("/")
        if suffix:
            return f"/app-next/campaigns/{campaign_slug}/{suffix}"
        return f"/app-next/campaigns/{campaign_slug}"

    def preferred_campaign_href(campaign_slug: str, suffix: str = "", frontend_mode: str = "gen2") -> str:
        if normalize_frontend_mode(frontend_mode) == "gen2":
            return gen2_campaign_href(campaign_slug, suffix)
        return flask_campaign_href(campaign_slug, suffix)

    def preferred_wiki_body_html(campaign_slug: str, body_html: str, frontend_mode: str = "gen2") -> str:
        normalized_frontend_mode = normalize_frontend_mode(frontend_mode)
        base = "/app-next/campaigns" if normalized_frontend_mode == "gen2" else "/campaigns"
        rewritten = re.sub(
            rf"(?:/app-next)?/campaigns/{re.escape(campaign_slug)}/(pages|sections)/",
            rf"{base}/{campaign_slug}/\1/",
            body_html,
        )
        rewritten = rewritten.replace(
            "/app-next/campaigns/{campaign_slug}/",
            f"{base}/{campaign_slug}/",
        )
        rewritten = rewritten.replace(
            "/campaigns/{campaign_slug}/",
            f"{base}/{campaign_slug}/",
        )
        return rewritten

    def get_public_wiki_page_image(campaign, page) -> dict[str, Any] | None:
        if not page.image_path:
            return None
        try:
            asset_record = get_campaign_asset_file_record(campaign, page.image_path)
        except CampaignContentError:
            return None
        if asset_record is None:
            return None
        return {
            "asset_ref": asset_record.asset_ref,
            "url": url_for("campaign_asset", campaign_slug=campaign.slug, asset_path=asset_record.asset_ref),
            "media_type": asset_record.media_type,
            "alt_text": page.image_alt or page.title,
            "caption": page.image_caption,
        }

    def serialize_public_wiki_page(
        campaign,
        page,
        *,
        include_image: bool = False,
        frontend_mode: str = "gen2",
    ) -> dict[str, Any]:
        payload = {
            "page_ref": page.route_slug,
            "title": page.title,
            "route_slug": page.route_slug,
            "href": preferred_campaign_href(
                campaign.slug,
                f"pages/{page.route_slug}",
                frontend_mode=frontend_mode,
            ),
            "section": page.section,
            "section_slug": slugify(page.section),
            "section_href": preferred_campaign_href(
                campaign.slug,
                f"sections/{slugify(page.section)}",
                frontend_mode=frontend_mode,
            ),
            "subsection": page.subsection,
            "page_type": page.page_type,
            "display_type": page.display_type,
            "summary": page.summary,
            "display_order": page.display_order,
            "reveal_after_session": page.reveal_after_session,
            "is_pinned": page.is_pinned,
        }
        if include_image:
            payload["image"] = get_public_wiki_page_image(campaign, page)
        return payload

    def serialize_public_wiki_page_with_body(
        campaign,
        page,
        body_html: str,
        *,
        frontend_mode: str = "gen2",
    ) -> dict[str, Any]:
        return {
            **serialize_public_wiki_page(
                campaign,
                page,
                include_image=True,
                frontend_mode=frontend_mode,
            ),
            "body_html": preferred_wiki_body_html(campaign.slug, body_html, frontend_mode=frontend_mode),
        }

    def serialize_public_wiki_section_group(
        campaign,
        section_name: str,
        pages: list[Any],
        *,
        frontend_mode: str = "gen2",
    ) -> dict[str, Any]:
        return {
            "section_name": section_name,
            "section_slug": slugify(section_name),
            "href": preferred_campaign_href(
                campaign.slug,
                f"sections/{slugify(section_name)}",
                frontend_mode=frontend_mode,
            ),
            "page_count": len(pages),
            "pages": [
                serialize_public_wiki_page(campaign, page, frontend_mode=frontend_mode)
                for page in pages
            ],
        }

    def serialize_public_wiki_section_navigation(
        campaign,
        pages: list[Any],
        *,
        frontend_mode: str = "gen2",
    ) -> list[dict[str, Any]]:
        grouped_pages_map: dict[str, list[Any]] = defaultdict(list)
        for page in pages:
            grouped_pages_map[page.section].append(page)
        return [
            {
                "section_name": section_name,
                "section_slug": slugify(section_name),
                "href": preferred_campaign_href(
                    campaign.slug,
                    f"sections/{slugify(section_name)}",
                    frontend_mode=frontend_mode,
                ),
                "page_count": len(grouped_pages_map[section_name]),
            }
            for section_name in sorted(grouped_pages_map, key=section_sort_key)
        ]

    def split_public_wiki_pages_by_subsection(
        campaign,
        section_name: str,
        pages: list[Any],
        *,
        frontend_mode: str = "gen2",
    ) -> dict[str, Any]:
        top_level_pages = [page for page in pages if not page.subsection]
        subsection_groups: dict[str, list[Any]] = defaultdict(list)
        for page in pages:
            if page.subsection:
                subsection_groups[page.subsection].append(page)

        ordered_subsection_groups = [
            {
                "subsection_name": subsection_name,
                "page_count": len(subsection_groups[subsection_name]),
                "pages": [
                    serialize_public_wiki_page(campaign, page, frontend_mode=frontend_mode)
                    for page in subsection_groups[subsection_name]
                ],
            }
            for subsection_name in sorted(
                subsection_groups,
                key=lambda subsection_name: subsection_sort_key(section_name, subsection_name),
            )
        ]
        return {
            "top_level_pages": [
                serialize_public_wiki_page(campaign, page, frontend_mode=frontend_mode)
                for page in top_level_pages
            ],
            "subsection_groups": ordered_subsection_groups,
            "show_subsections": bool(ordered_subsection_groups),
        }

    def serialize_page_file_record(campaign_slug: str, record) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        is_visible = campaign.is_page_visible(record.page) if campaign is not None else False
        return {
            "page_ref": record.page_ref,
            "relative_path": record.relative_path,
            "updated_at": record.updated_at,
            "metadata": record.metadata,
            "body_markdown": record.body_markdown,
            "page": {
                **serialize_page(record.page),
                "is_visible": is_visible,
            },
        }

    def serialize_page_file_summary(campaign_slug: str, record) -> dict[str, Any]:
        payload = serialize_page_file_record(campaign_slug, record)
        payload.pop("body_markdown", None)
        return payload

    def _campaign_session_service():
        return current_app.extensions.get("campaign_session_service")

    def _character_repository():
        return current_app.extensions.get("character_repository")

    def _build_content_page_removal_safety(
        campaign_slug: str,
        campaign,
        page_records: list[object],
    ) -> dict[str, dict[str, object]]:
        session_service = _campaign_session_service()
        character_repository = _character_repository()
        session_articles = (
            list(session_service.list_articles(campaign_slug))
            if session_service is not None
            else []
        )
        character_records = (
            list(character_repository.list_characters(campaign_slug))
            if character_repository is not None
            else []
        )
        return build_dm_player_wiki_removal_safety_index(
            campaign_slug,
            campaign,
            page_records,
            session_articles=session_articles,
            character_records=character_records,
        )

    def _build_content_page_file_payload(
        campaign_slug: str,
        record,
        *,
        removal_safety: dict[str, object] | None = None,
        include_body: bool = False,
    ) -> dict[str, Any]:
        payload = (
            serialize_page_file_record(campaign_slug, record)
            if include_body
            else serialize_page_file_summary(campaign_slug, record)
        )
        normalized_safety = dict(removal_safety or {})
        payload["removal_safety"] = normalized_safety
        payload["can_hard_delete"] = bool(normalized_safety.get("can_hard_delete", True))
        payload["hard_delete_blockers"] = list(normalized_safety.get("hard_delete_blockers", []) or [])
        payload["removal_status_label"] = str(
            normalized_safety.get("removal_status_label") or "Hard delete available"
        )
        payload["removal_guidance"] = str(
            normalized_safety.get("removal_guidance")
            or "Hard delete is available after confirmation."
        )
        return payload

    def _parse_force_delete_flag() -> bool:
        raw_force = request.args.get("force")
        if raw_force is not None:
            return str(raw_force).strip().lower() in {"1", "true", "yes", "on"}
        return False

    def _parse_force_delete_payload(payload: dict[str, Any]) -> bool:
        if not payload:
            return False
        raw_force = payload.get("force")
        if isinstance(raw_force, bool):
            return raw_force
        if raw_force is None:
            return False
        return str(raw_force).strip().lower() in {"1", "true", "yes", "on"}

    def serialize_visibility_map(campaign_slug: str) -> dict[str, Any]:
        visibility = {
            scope: {
                "effective": get_effective_campaign_visibility(campaign_slug, scope),
                "can_access": can_access_campaign_scope(campaign_slug, scope),
            }
            for scope in CAMPAIGN_VISIBILITY_SCOPES
        }
        user = get_current_user()
        if user is not None and (user.is_admin or get_campaign_role(campaign_slug) == "dm"):
            for scope in CAMPAIGN_VISIBILITY_SCOPES:
                visibility[scope]["configured"] = get_campaign_scope_visibility(campaign_slug, scope)
        return visibility

    def serialize_campaign_control_visibility_row(campaign_slug: str, scope: str) -> dict[str, Any]:
        user = get_current_user()
        include_private = bool(user and user.is_admin)
        configured_visibility = get_auth_store().get_campaign_visibility_setting(campaign_slug, scope)
        current_visibility = configured_visibility.visibility if configured_visibility is not None else ""
        effective_visibility = get_effective_campaign_visibility(campaign_slug, scope)
        default_visibility = get_campaign_default_scope_visibility(campaign_slug, scope)
        selected_visibility = current_visibility or default_visibility
        return {
            "scope": scope,
            "label": CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope],
            "selected_visibility": selected_visibility,
            "selected_visibility_label": VISIBILITY_LABELS.get(selected_visibility, selected_visibility),
            "configured_visibility": current_visibility,
            "configured_visibility_label": VISIBILITY_LABELS.get(current_visibility, "") if current_visibility else "",
            "default_visibility": default_visibility,
            "default_visibility_label": VISIBILITY_LABELS.get(default_visibility, default_visibility),
            "effective_visibility": effective_visibility,
            "effective_visibility_label": VISIBILITY_LABELS[effective_visibility],
            "choices": list_visibility_choices(include_private=include_private),
            "is_overridden_by_campaign": scope != "campaign"
            and effective_visibility != current_visibility
            and effective_visibility == get_effective_campaign_visibility(campaign_slug, "campaign"),
        }

    def serialize_session_record(record) -> dict[str, Any]:
        return {
            "id": record.id,
            "campaign_slug": record.campaign_slug,
            "status": record.status,
            "started_at": serialize_datetime(record.started_at),
            "started_by_user_id": record.started_by_user_id,
            "ended_at": serialize_datetime(record.ended_at),
            "ended_by_user_id": record.ended_by_user_id,
            "is_active": record.is_active,
        }

    def serialize_session_log_summary(summary) -> dict[str, Any]:
        return {
            "session": serialize_session_record(summary.session),
            "message_count": summary.message_count,
            "last_message_at": serialize_datetime(summary.last_message_at),
            "detail_url": url_for(
                ".session_log_detail",
                campaign_slug=summary.session.campaign_slug,
                session_id=summary.session.id,
            ),
        }

    def serialize_session_article_image(campaign_slug: str, article_id: int, image) -> dict[str, Any]:
        return {
            "filename": image.filename,
            "media_type": image.media_type,
            "alt_text": image.alt_text,
            "caption": image.caption,
            "updated_at": serialize_datetime(image.updated_at),
            "url": url_for(".session_article_image", campaign_slug=campaign_slug, article_id=article_id),
        }

    def build_session_article_source_metadata(
        campaign,
        source_kind: str,
        source_ref: str,
    ) -> dict[str, str]:
        metadata: dict[str, str] = {
            "title": "",
            "label": "",
            "action_label": "",
            "missing_message": "",
            "url": "",
        }
        if campaign is None or not source_kind or not source_ref:
            return metadata

        if source_kind == SESSION_ARTICLE_SOURCE_KIND_PAGE:
            try:
                record = get_campaign_page_store().get_page_record(
                    campaign.slug,
                    source_ref,
                    include_body=False,
                )
            except ValueError:
                record = None

            metadata["label"] = "published wiki page"
            metadata["action_label"] = "View published page"
            metadata["missing_message"] = (
                "The original published wiki page is not currently visible in the player wiki."
            )
            if record is not None and campaign.is_page_visible(record.page):
                metadata["title"] = record.page.title
                metadata["url"] = url_for(
                    "page_view",
                    campaign_slug=campaign.slug,
                    page_slug=record.page.route_slug,
                )
            elif record is not None:
                metadata["title"] = record.page.title
            return metadata

        if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
            systems_service = current_app.extensions["systems_service"]
            entry = systems_service.get_entry_by_slug_for_campaign(campaign.slug, source_ref)
            metadata["label"] = "Systems entry"
            metadata["action_label"] = "View Systems entry"
            metadata["missing_message"] = (
                "The original Systems entry is not currently visible in this campaign."
            )
            if entry is not None and can_access_campaign_systems_entry(campaign.slug, entry.slug):
                metadata["title"] = entry.title
                metadata["url"] = url_for(
                    "campaign_systems_entry_detail",
                    campaign_slug=campaign.slug,
                    entry_slug=entry.slug,
                )
            return metadata

        return metadata

    def build_session_article_links(
        campaign,
        campaign_slug: str | None,
        article,
        source: dict[str, str],
        converted_page=None,
    ) -> dict[str, str]:
        source_kind, _ = parse_session_article_source_ref(article.source_page_ref)
        links = {
            "source_url": source.get("url", ""),
            "published_page_url": "",
            "player_wiki_editor_url": "",
            "convert_url": "",
        }
        converted_page_is_visible = (
            converted_page is not None
            and campaign is not None
            and campaign.is_page_visible(converted_page)
        )

        if converted_page is not None and converted_page_is_visible and campaign_slug:
            links["published_page_url"] = url_for(
                "page_view",
                campaign_slug=campaign_slug,
                page_slug=converted_page.route_slug,
            )

        if source_kind == "" and converted_page is None and campaign_slug:
            links["player_wiki_editor_url"] = url_for(
                "campaign_dm_content_new_player_wiki_page_from_session_article",
                campaign_slug=campaign_slug,
                article_id=article.id,
            )
            links["convert_url"] = url_for(
                "campaign_session_convert_article_view",
                campaign_slug=campaign_slug,
                article_id=article.id,
            )

        return links

    def serialize_session_article(
        campaign_slug: str,
        article,
        article_image=None,
        *,
        campaign=None,
        converted_pages: dict[int, Any] | None = None,
    ) -> dict[str, Any]:
        if campaign is None:
            campaign = get_repository().get_campaign(campaign_slug)
        source_kind, source_ref = parse_session_article_source_ref(article.source_page_ref)
        converted_pages = converted_pages or {}
        converted_page = converted_pages.get(article.id)
        if converted_page is None and campaign is not None:
            converted_page = list_published_pages_for_session_articles(campaign, [article.id]).get(article.id)

        source = build_session_article_source_metadata(
            campaign,
            source_kind,
            source_ref,
        )
        converted_page_is_visible = (
            converted_page is not None
            and campaign is not None
            and campaign.is_page_visible(converted_page)
        )
        return {
            "id": article.id,
            "campaign_slug": article.campaign_slug,
            "title": article.title,
            "body_markdown": article.body_markdown,
            "body_format": "html" if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS else "markdown",
            "source_page_ref": article.source_page_ref,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "status": article.status,
            "created_at": serialize_datetime(article.created_at),
            "created_by_user_id": article.created_by_user_id,
            "revealed_at": serialize_datetime(article.revealed_at),
            "revealed_by_user_id": article.revealed_by_user_id,
            "revealed_in_session_id": article.revealed_in_session_id,
            "is_revealed": article.is_revealed,
            "links": build_session_article_links(
                campaign,
                campaign.slug if campaign is not None else None,
                article,
                source,
                converted_page=converted_page,
            ),
            "source": {
                "title": str(source.get("title") or ""),
                "label": str(source.get("label") or ""),
                "action_label": str(source.get("action_label") or ""),
                "missing_message": str(source.get("missing_message") or ""),
            },
            "converted_page": (
                {
                    "title": converted_page.title,
                    "is_visible": converted_page_is_visible,
                    "reveal_after_session": converted_page.reveal_after_session,
                }
                if converted_page is not None
                else None
            ),
            "image": (
                serialize_session_article_image(campaign_slug, article.id, article_image)
                if article_image is not None
                else None
            ),
        }

    def serialize_session_message(
        campaign_slug: str,
        message,
        article_lookup: dict[int, Any],
        article_images: dict[int, Any],
        *,
        campaign=None,
        converted_pages: dict[int, Any] | None = None,
    ) -> dict[str, Any]:
        article = article_lookup.get(message.article_id) if message.article_id is not None else None
        recipient_user = (
            get_auth_store().get_user_by_id(message.recipient_user_id)
            if message.recipient_scope == "player" and message.recipient_user_id
            else None
        )
        recipient_label = str(recipient_user.display_name or "") if recipient_user is not None else ""
        if not recipient_label and message.recipient_user_id:
            recipient_label = f"User {message.recipient_user_id}"
        if message.recipient_scope == "dm_only":
            recipient_label = "DM"
        elif not recipient_label and message.recipient_scope == "player":
            recipient_label = "Unknown player"
        return {
            "id": message.id,
            "session_id": message.session_id,
            "campaign_slug": message.campaign_slug,
            "message_type": message.message_type,
            "body_text": message.body_text,
            "author_user_id": message.author_user_id,
            "author_display_name": message.author_display_name,
            "article_id": message.article_id,
            "created_at": serialize_datetime(message.created_at),
            "recipient_scope": message.recipient_scope,
            "recipient_user_id": message.recipient_user_id,
            "recipient_label": recipient_label,
            "article": (
                serialize_session_article(
                    campaign_slug,
                    article,
                    article_images.get(article.id),
                    campaign=campaign,
                    converted_pages=converted_pages,
                )
                if article is not None
                else None
            ),
        }

    def serialize_app_state() -> dict[str, Any]:
        return {
            **build_app_metadata(current_app.config),
            "db_path": str(current_app.config["DB_PATH"]),
            "campaigns_dir": str(current_app.config["CAMPAIGNS_DIR"]),
        }

    def refresh_repository_store() -> None:
        repository_store = current_app.extensions.get("repository_store")
        if repository_store is not None:
            repository_store.refresh()

    def get_campaign_page_store():
        return current_app.extensions["campaign_page_store"]

    def get_campaign_asset_file(campaign, asset_path: str) -> Path | None:
        normalized_asset_path = str(asset_path or "").strip().replace("\\", "/")
        if not normalized_asset_path:
            return None

        assets_root = Path(campaign.assets_dir).resolve()
        candidate = (assets_root / normalized_asset_path).resolve()
        if assets_root not in candidate.parents and candidate != assets_root:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def get_pullable_session_wiki_page_record(
        campaign,
        page_ref: str,
        *,
        include_body: bool = False,
    ):
        try:
            record = get_campaign_page_store().get_page_record(
                campaign.slug,
                page_ref,
                include_body=include_body,
            )
        except ValueError:
            return None
        if record is None or not campaign.is_page_visible(record.page):
            return None
        return record

    def get_pullable_session_systems_entry(campaign_slug: str, entry_slug: str):
        normalized_entry_slug = str(entry_slug or "").strip()
        if not normalized_entry_slug:
            return None
        if not can_access_campaign_scope(campaign_slug, "systems"):
            return None

        entry = current_app.extensions["systems_service"].get_entry_by_slug_for_campaign(
            campaign_slug,
            normalized_entry_slug,
        )
        if entry is None or not can_access_campaign_systems_entry(campaign_slug, entry.slug):
            return None
        return entry

    def build_session_article_source_search_results(campaign_slug: str, query: str, *, limit: int = 30) -> list[dict[str, str]]:
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        return build_shared_session_article_source_search_results(
            campaign=campaign,
            campaign_slug=campaign_slug,
            query=query,
            page_store=get_campaign_page_store(),
            systems_service=current_app.extensions["systems_service"],
            can_access_systems=can_access_campaign_scope(campaign_slug, "systems"),
            can_access_systems_entry=lambda entry_slug: can_access_campaign_systems_entry(campaign_slug, entry_slug),
            limit=limit,
        )

    def build_session_message_recipient_player_choices(campaign_slug: str) -> list[dict[str, object]]:
        return build_active_player_choices(get_auth_store(), campaign_slug)

    def build_session_payload(campaign_slug: str) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        session_service = current_app.extensions["campaign_session_service"]
        can_manage_session = can_manage_campaign_session(campaign_slug)
        can_post_messages = can_post_campaign_session_messages(campaign_slug)
        active_session = session_service.get_active_session(campaign_slug)

        article_lookup: dict[int, Any] = {}
        article_images: dict[int, Any] = {}
        if can_manage_session:
            articles = session_service.list_articles(campaign_slug)
            article_lookup = {article.id: article for article in articles}
            if article_lookup:
                article_images = session_service.list_article_images(list(article_lookup))
        elif active_session is not None:
            articles = session_service.list_articles(campaign_slug, statuses=("revealed",))
            article_lookup = {article.id: article for article in articles}
            if article_lookup:
                article_images = session_service.list_article_images(list(article_lookup))

        converted_pages = (
            list_published_pages_for_session_articles(campaign, list(article_lookup))
            if article_lookup
            else {}
        )

        messages = []
        if active_session is not None:
            current_user = get_current_user()
            messages = [
                serialize_session_message(
                    campaign_slug,
                    message,
                    article_lookup,
                    article_images,
                    campaign=campaign,
                    converted_pages=converted_pages,
                )
                for message in session_service.list_messages(
                    active_session.id,
                    viewer_user_id=int(current_user.id) if current_user else None,
                    can_manage_session=can_manage_session,
                )
            ]

        payload: dict[str, Any] = {
            "campaign": serialize_campaign(campaign),
            "permissions": {
                "can_manage_session": can_manage_session,
                "can_post_messages": can_post_messages,
            },
            "active_session": serialize_session_record(active_session) if active_session is not None else None,
            "messages": messages,
            "session_message_recipient_player_choices": (
                build_session_message_recipient_player_choices(campaign_slug)
                if can_post_messages
                else []
            ),
        }

        if can_manage_session:
            payload["staged_articles"] = [
                serialize_session_article(
                    campaign_slug,
                    article,
                    article_images.get(article.id),
                    campaign=campaign,
                    converted_pages=converted_pages,
                )
                for article in article_lookup.values()
                if not article.is_revealed
            ]
            payload["revealed_articles"] = [
                serialize_session_article(
                    campaign_slug,
                    article,
                    article_images.get(article.id),
                    campaign=campaign,
                    converted_pages=converted_pages,
                )
                for article in article_lookup.values()
                if article.is_revealed
            ]
            payload["session_logs"] = [
                serialize_session_log_summary(summary)
                for summary in session_service.list_session_logs(campaign_slug, limit=20)
            ]

        show_session_dm_passive_scores = can_manage_session and is_dnd_5e_system(campaign.system)
        payload["show_session_dm_passive_scores"] = show_session_dm_passive_scores
        if show_session_dm_passive_scores:
            payload["session_dm_passive_scores"] = present_session_dm_passive_score_rows(
                campaign=campaign,
                records=get_character_repository().list_visible_characters(campaign.slug),
                systems_service=current_app.extensions["systems_service"],
                campaign_page_records=list_visible_character_page_records(campaign.slug, campaign),
            )

        return payload

    def build_live_hash(*parts: object) -> str:
        normalized_parts = [str(part).strip().lower() for part in parts]
        digest = hashlib.sha1("||".join(normalized_parts).encode("utf-8")).hexdigest()
        return digest[:12]

    def build_session_live_view_token(campaign_slug: str, session_subpage: str) -> str:
        normalized_subpage = "session" if str(session_subpage or "").strip().lower() != "dm" else "dm"
        current_preferences = get_current_user_preferences()
        return build_live_hash(
            "session",
            normalized_subpage,
            current_preferences.session_chat_order,
            "1" if can_manage_campaign_session(campaign_slug) else "0",
            "1" if can_post_campaign_session_messages(campaign_slug) else "0",
        )

    def build_combat_live_view_token(
        campaign_slug: str,
        *,
        selected_combatant_id: int | None = None,
    ) -> str:
        return build_live_hash(
            "combat",
            "player",
            "1" if can_manage_campaign_combat(campaign_slug) else "0",
            str(selected_combatant_id or ""),
            *sorted(get_owned_character_slugs(campaign_slug)),
        )

    def parse_live_revision_header() -> int | None:
        raw_value = request.headers.get("X-Live-Revision", "").strip()
        if not raw_value:
            return None
        try:
            parsed_value = int(raw_value)
        except ValueError:
            return None
        return parsed_value if parsed_value >= 0 else None

    def parse_live_view_token_header() -> str:
        return request.headers.get("X-Live-View-Token", "").strip()

    def should_short_circuit_live_session(*, live_revision: int, live_view_token: str) -> bool:
        requested_revision = parse_live_revision_header()
        requested_view_token = parse_live_view_token_header()
        if requested_revision is None or not requested_view_token:
            return False
        return requested_revision == live_revision and requested_view_token == live_view_token

    def should_short_circuit_live_response(*, live_revision: int, live_view_token: str) -> bool:
        requested_revision = parse_live_revision_header()
        requested_view_token = parse_live_view_token_header()
        if requested_revision is None or not requested_view_token:
            return False
        return requested_revision == live_revision and requested_view_token == live_view_token

    def serialize_dm_statblock(statblock) -> dict[str, Any]:
        return {
            "id": statblock.id,
            "campaign_slug": statblock.campaign_slug,
            "title": statblock.title,
            "body_markdown": statblock.body_markdown,
            "source_filename": statblock.source_filename,
            "subsection": statblock.subsection,
            "armor_class": statblock.armor_class,
            "max_hp": statblock.max_hp,
            "speed_text": statblock.speed_text,
            "movement_total": statblock.movement_total,
            "initiative_bonus": statblock.initiative_bonus,
            "parser_feedback": build_statblock_parser_feedback(statblock),
            "created_at": serialize_datetime(statblock.created_at),
            "updated_at": serialize_datetime(statblock.updated_at),
            "created_by_user_id": statblock.created_by_user_id,
            "updated_by_user_id": statblock.updated_by_user_id,
        }

    def serialize_condition_definition(definition) -> dict[str, Any]:
        return {
            "id": definition.id,
            "campaign_slug": definition.campaign_slug,
            "name": definition.name,
            "description_markdown": definition.description_markdown,
            "created_at": serialize_datetime(definition.created_at),
            "updated_at": serialize_datetime(definition.updated_at),
            "created_by_user_id": definition.created_by_user_id,
            "updated_by_user_id": definition.updated_by_user_id,
        }

    def build_dm_content_payload(campaign_slug: str) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        service = current_app.extensions["campaign_dm_content_service"]
        can_manage_content = can_manage_campaign_content(campaign_slug)
        can_manage_session = can_manage_campaign_session(campaign_slug)
        can_manage_systems = can_manage_campaign_systems(campaign_slug)
        statblocks = service.list_statblocks(campaign_slug)
        conditions = service.list_condition_definitions(campaign_slug)
        session_service = _campaign_session_service()
        systems_service = current_app.extensions.get("systems_service")
        player_wiki_page_count = len(campaign.pages) if can_manage_content else 0
        staged_article_count = (
            len(session_service.list_articles(campaign_slug, statuses=("staged",)))
            if can_manage_session and session_service is not None
            else 0
        )
        systems_lane_count = (
            len(systems_service.list_campaign_source_states(campaign_slug))
            if can_manage_systems and systems_service is not None
            else 0
        )

        return {
            "campaign": serialize_campaign(campaign),
            "permissions": {
                "can_manage_dm_content": can_manage_campaign_dm_content(campaign_slug),
            },
            "statblocks": [serialize_dm_statblock(statblock) for statblock in statblocks],
            "conditions": [serialize_condition_definition(definition) for definition in conditions],
            "subpage_counts": {
                "statblocks": len(statblocks),
                "conditions": len(conditions),
                "player_wiki": player_wiki_page_count,
                "staged_articles": staged_article_count,
                "systems": systems_lane_count,
            },
        }

    def serialize_campaign_config_record(record) -> dict[str, Any]:
        return {
            "campaign_slug": record.campaign_slug,
            "updated_at": record.updated_at,
            "config": record.config,
            "editable_fields": sorted(
                [
                    "current_session",
                    "source_wiki_root",
                    "summary",
                    "system",
                    "systems_library",
                    "title",
                ]
            ),
        }

    def serialize_asset_file_summary(campaign_slug: str, record) -> dict[str, Any]:
        return {
            "asset_ref": record.asset_ref,
            "relative_path": record.relative_path,
            "size_bytes": record.size_bytes,
            "media_type": record.media_type,
            "updated_at": record.updated_at,
            "url": url_for("campaign_asset", campaign_slug=campaign_slug, asset_path=record.asset_ref),
        }

    def serialize_asset_file_record(campaign_slug: str, record, *, include_data: bool = False) -> dict[str, Any]:
        payload = serialize_asset_file_summary(campaign_slug, record)
        if include_data:
            payload["data_base64"] = base64.b64encode(record.file_path.read_bytes()).decode("ascii")
        return payload

    def serialize_systems_library(library) -> dict[str, Any] | None:
        if library is None:
            return None
        return {
            "library_slug": library.library_slug,
            "title": library.title,
            "system_code": library.system_code,
            "status": library.status,
            "created_at": serialize_datetime(library.created_at),
            "updated_at": serialize_datetime(library.updated_at),
        }

    def serialize_systems_source_state(campaign_slug: str, state) -> dict[str, Any]:
        systems_service = current_app.extensions["systems_service"]
        return {
            "source_id": state.source.source_id,
            "title": state.source.title,
            "library_slug": state.source.library_slug,
            "license_class": state.source.license_class,
            "license_class_label": LICENSE_CLASS_LABELS.get(
                state.source.license_class,
                state.source.license_class.replace("_", " ").title(),
            ),
            "public_visibility_allowed": state.source.public_visibility_allowed,
            "requires_unofficial_notice": state.source.requires_unofficial_notice,
            "status": state.source.status,
            "is_enabled": state.is_enabled,
            "default_visibility": state.default_visibility,
            "is_configured": state.is_configured,
            "entry_count": (
                systems_service.count_entries_for_source(campaign_slug, state.source.source_id)
                if state.is_enabled
                else 0
            ),
            "permissions": {
                "can_access": can_access_campaign_systems_source(campaign_slug, state.source.source_id),
                "can_manage": can_manage_campaign_systems(campaign_slug),
            },
        }

    def serialize_systems_entry_summary(entry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "library_slug": entry.library_slug,
            "source_id": entry.source_id,
            "entry_key": entry.entry_key,
            "entry_type": entry.entry_type,
            "entry_type_label": systems_entry_type_label(entry.entry_type),
            "slug": entry.slug,
            "title": entry.title,
            "source_page": entry.source_page,
            "source_path": entry.source_path,
            "player_safe_default": entry.player_safe_default,
            "dm_heavy": entry.dm_heavy,
            "created_at": serialize_datetime(entry.created_at),
            "updated_at": serialize_datetime(entry.updated_at),
        }

    def serialize_systems_entry_record(campaign_slug: str, entry) -> dict[str, Any]:
        systems_service = current_app.extensions["systems_service"]
        source_state = systems_service.get_campaign_source_state(campaign_slug, entry.source_id)
        override = systems_service.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
        return {
            **serialize_systems_entry_summary(entry),
            "metadata": entry.metadata,
            "body": entry.body,
            "rendered_html": entry.rendered_html,
            "source_state": (
                serialize_systems_source_state(campaign_slug, source_state)
                if source_state is not None
                else None
            ),
            "override": (
                {
                    "entry_key": override.entry_key,
                    "visibility_override": override.visibility_override,
                    "is_enabled_override": override.is_enabled_override,
                    "updated_at": serialize_datetime(override.updated_at),
                    "updated_by_user_id": override.updated_by_user_id,
                }
                if override is not None
                else None
            ),
        }

    def serialize_systems_rules_reference_result(entry) -> dict[str, Any]:
        metadata = dict(entry.metadata or {})
        reference_scope = ""
        if entry.entry_type == "book":
            scope_parts = [str(metadata.get("section_label") or "").strip()]
            chapter_title = str(metadata.get("chapter_title") or "").strip()
            if chapter_title and chapter_title != entry.title:
                scope_parts.append(chapter_title)
            reference_scope = " | ".join(part for part in scope_parts if part)
        elif entry.entry_type == "rule":
            facets = [
                str(value).strip()
                for value in list(metadata.get("rule_facets") or [])
                if str(value).strip()
            ]
            aliases = [
                str(value).strip()
                for value in list(metadata.get("aliases") or [])
                if str(value).strip()
            ]
            summary_values = facets or aliases
            if summary_values:
                reference_scope = ", ".join(summary_values[:3])

        return {
            "title": entry.title,
            "entry_type": entry.entry_type,
            "entry_type_label": SYSTEMS_ENTRY_TYPE_LABELS.get(
                entry.entry_type,
                entry.entry_type.replace("_", " ").title(),
            ),
            "source_id": entry.source_id,
            "slug": entry.slug,
            "reference_scope": reference_scope,
        }

    def filter_accessible_systems_entries(
        campaign_slug: str,
        entries: list[object],
        *,
        limit: int | None = None,
    ) -> list[object]:
        accessible_entries = [
            entry
            for entry in entries
            if can_access_campaign_systems_entry(campaign_slug, str(getattr(entry, "slug", "") or ""))
        ]
        if limit is not None:
            return accessible_entries[:limit]
        return accessible_entries

    def list_accessible_campaign_source_entries(
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[object]:
        systems_service = current_app.extensions["systems_service"]
        entries = systems_service.list_entries_for_campaign_source(
            campaign_slug,
            source_id,
            entry_type=entry_type,
            query=query,
            limit=None,
        )
        return filter_accessible_systems_entries(campaign_slug, entries, limit=limit)

    def serialize_systems_import_run(import_run) -> dict[str, Any]:
        return {
            "id": import_run.id,
            "library_slug": import_run.library_slug,
            "source_id": import_run.source_id,
            "status": import_run.status,
            "import_version": import_run.import_version,
            "source_path": import_run.source_path,
            "summary": import_run.summary,
            "started_at": serialize_datetime(import_run.started_at),
            "completed_at": serialize_datetime(import_run.completed_at),
            "started_by_user_id": import_run.started_by_user_id,
        }

    def serialize_systems_import_result(result) -> dict[str, Any]:
        return {
            "source_id": result.source_id,
            "import_run_id": result.import_run_id,
            "import_version": result.import_version,
            "imported_count": result.imported_count,
            "imported_by_type": result.imported_by_type,
            "source_files": result.source_files,
        }

    def serialize_systems_override(override) -> dict[str, Any]:
        return {
            "entry_key": override.entry_key,
            "visibility_override": override.visibility_override,
            "is_enabled_override": override.is_enabled_override,
            "updated_at": serialize_datetime(override.updated_at),
            "updated_by_user_id": override.updated_by_user_id,
        }

    def serialize_systems_override_row(campaign_slug: str, library_slug: str, override) -> dict[str, Any]:
        systems_service = current_app.extensions["systems_service"]
        entry = systems_service.store.get_entry(library_slug, override.entry_key)
        source_state = (
            systems_service.get_campaign_source_state(campaign_slug, entry.source_id)
            if entry is not None
            else None
        )
        if override.visibility_override:
            visibility_label = VISIBILITY_LABELS.get(override.visibility_override, override.visibility_override)
        else:
            visibility_label = "Inherit source default"
        if override.is_enabled_override is None:
            enablement_label = "Inherit source enablement"
        elif override.is_enabled_override:
            enablement_label = "Enabled"
        else:
            enablement_label = "Disabled"
        return {
            **serialize_systems_override(override),
            "entry_title": entry.title if entry is not None else "Unknown entry",
            "entry_type": entry.entry_type if entry is not None else "",
            "entry_type_label": (
                systems_entry_type_label(entry.entry_type)
                if entry is not None
                else ""
            ),
            "entry_slug": entry.slug if entry is not None else "",
            "entry_href": (
                url_for(
                    "campaign_systems_entry_detail",
                    campaign_slug=campaign_slug,
                    entry_slug=entry.slug,
                )
                if entry is not None and can_access_campaign_systems_entry(campaign_slug, entry.slug)
                else ""
            ),
            "source_id": entry.source_id if entry is not None else "",
            "source_label": (
                f"{source_state.source.title} ({source_state.source.source_id})"
                if source_state is not None
                else (entry.source_id if entry is not None else "")
            ),
            "visibility_label": visibility_label,
            "enablement_label": enablement_label,
        }

    def serialize_custom_systems_entry(campaign_slug: str, entry) -> dict[str, Any]:
        systems_service = current_app.extensions["systems_service"]
        override = systems_service.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
        is_archived = bool(override is not None and override.is_enabled_override is False)
        visibility = (
            override.visibility_override
            if override is not None and override.visibility_override
            else systems_service.get_default_entry_visibility_for_campaign(campaign_slug, entry)
        )
        metadata = dict(entry.metadata or {})
        body = dict(entry.body or {})
        return {
            **serialize_systems_entry_summary(entry),
            "visibility": visibility,
            "visibility_label": VISIBILITY_LABELS.get(visibility, visibility),
            "status_label": "Archived" if is_archived else "Active",
            "is_archived": is_archived,
            "provenance": str(metadata.get("provenance") or entry.source_path or ""),
            "search_metadata": str(metadata.get("search_metadata") or ""),
            "body_markdown": str(body.get("markdown") or metadata.get("body_markdown") or ""),
            "rendered_html": entry.rendered_html,
            "href": (
                url_for(
                    "campaign_systems_entry_detail",
                    campaign_slug=campaign_slug,
                    entry_slug=entry.slug,
                )
                if can_access_campaign_systems_entry(campaign_slug, entry.slug)
                else ""
            ),
            "override": serialize_systems_override(override) if override is not None else None,
        }

    def serialize_systems_import_run_review(import_run) -> dict[str, Any]:
        summary = dict(import_run.summary or {})
        imported_by_type = summary.get("imported_by_type")
        type_summary = []
        if isinstance(imported_by_type, dict):
            for entry_type, count in sorted(imported_by_type.items()):
                type_summary.append(
                    {
                        "entry_type": str(entry_type),
                        "entry_type_label": SYSTEMS_ENTRY_TYPE_LABELS.get(
                            str(entry_type),
                            str(entry_type).replace("_", " ").title(),
                        ),
                        "count": count,
                    }
                )
        source_files = summary.get("source_files")
        return {
            "id": import_run.id,
            "library_slug": import_run.library_slug,
            "source_id": import_run.source_id,
            "status": import_run.status,
            "import_version": import_run.import_version,
            "imported_count": summary.get("imported_count"),
            "type_summary": type_summary,
            "source_files": source_files if isinstance(source_files, list) else [],
            "source_file_count": len(source_files) if isinstance(source_files, list) else None,
            "error": str(summary.get("error") or ""),
            "started_at": serialize_datetime(import_run.started_at),
            "completed_at": serialize_datetime(import_run.completed_at),
            "started_by_user_id": import_run.started_by_user_id,
        }

    def build_dm_content_systems_payload(campaign_slug: str) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if not can_manage_campaign_systems(campaign_slug):
            if get_current_user() is None:
                raise PermissionError("Authentication required.")
            raise RuntimeError("You do not have permission to manage systems.")

        user = get_current_user()
        include_private = bool(user and user.is_admin)
        systems_service = current_app.extensions["systems_service"]
        policy = systems_service.get_campaign_policy(campaign_slug)
        library = systems_service.get_campaign_library(campaign_slug)
        library_slug = policy.library_slug if policy is not None else systems_service.get_campaign_library_slug(campaign_slug)
        source_states = systems_service.list_campaign_source_states(campaign_slug)
        systems_scope_visibility = get_effective_campaign_visibility(campaign_slug, "systems")

        visibility_choices = list_visibility_choices(include_private=include_private)
        source_rows = []
        for state in source_states:
            source_rows.append(
                {
                    **serialize_systems_source_state(campaign_slug, state),
                    "selected_visibility": state.default_visibility,
                    "entry_count": systems_service.count_entries_for_source(campaign_slug, state.source.source_id),
                    "choices": [
                        {
                            **choice,
                            "disabled": choice["value"] == "public" and not state.source.public_visibility_allowed,
                        }
                        for choice in visibility_choices
                    ],
                }
            )

        entry_override_rows = []
        if library_slug:
            entry_override_rows = [
                serialize_systems_override_row(campaign_slug, library_slug, override)
                for override in systems_service.store.list_campaign_entry_overrides(campaign_slug, library_slug)
            ]

        custom_entry_source_rows = []
        custom_entry_count = 0
        for state in source_states:
            if state.source.license_class != "custom_campaign":
                continue
            entries = systems_service.store.list_entries_for_source(
                state.source.library_slug,
                state.source.source_id,
                limit=None,
            )
            custom_entries = [serialize_custom_systems_entry(campaign_slug, entry) for entry in entries]
            active_entry_count = sum(1 for entry in custom_entries if not entry["is_archived"])
            custom_entry_count += len(custom_entries)
            custom_entry_source_rows.append(
                {
                    "source_id": state.source.source_id,
                    "title": state.source.title,
                    "is_enabled": state.is_enabled,
                    "default_visibility": state.default_visibility,
                    "default_visibility_label": VISIBILITY_LABELS.get(
                        state.default_visibility,
                        state.default_visibility,
                    ),
                    "entry_count": len(custom_entries),
                    "active_entry_count": active_entry_count,
                    "archived_entry_count": len(custom_entries) - active_entry_count,
                    "entries": custom_entries,
                }
            )

        import_run_rows = []
        if library_slug:
            import_run_rows = [
                serialize_systems_import_run_review(import_run)
                for import_run in systems_service.store.list_import_runs(library_slug=library_slug, limit=10)
            ]

        entry_type_labels = systems_entry_type_choice_labels(library_slug)
        import_source_choices = [
            {
                "source_id": state.source.source_id,
                "title": state.source.title,
                "license_class_label": LICENSE_CLASS_LABELS.get(
                    state.source.license_class,
                    state.source.license_class.replace("_", " ").title(),
                ),
                "entry_count": systems_service.count_entries_for_source(campaign_slug, state.source.source_id),
            }
            for state in source_states
            if state.source.source_id != "RULES" and state.source.license_class != "custom_campaign"
        ]

        return {
            "campaign": serialize_campaign(campaign),
            "library": serialize_systems_library(library),
            "systems_library": library_slug or "",
            "systems_scope_visibility_label": VISIBILITY_LABELS.get(
                systems_scope_visibility,
                systems_scope_visibility,
            ),
            "policy": {
                "allow_dm_shared_core_entry_edits": bool(policy and policy.allow_dm_shared_core_entry_edits),
                "proprietary_acknowledged": bool(policy and policy.proprietary_acknowledged_at is not None),
            },
            "source_rows": source_rows,
            "source_count": len(source_rows),
            "has_proprietary_sources": any(row["license_class"] == "proprietary_private" for row in source_rows),
            "entry_override_rows": entry_override_rows,
            "entry_override_count": len(entry_override_rows),
            "custom_entry_source_rows": custom_entry_source_rows,
            "custom_entry_count": custom_entry_count,
            "custom_entry_default_visibility": systems_service.get_custom_campaign_entry_default_visibility(campaign_slug),
            "custom_entry_type_choices": [
                {
                    "value": entry_type,
                    "label": entry_type_labels.get(entry_type, systems_entry_type_label(entry_type)),
                }
                for entry_type in sorted(entry_type_labels, key=systems_entry_type_sort_key)
            ],
            "custom_entry_visibility_choices": visibility_choices,
            "import_source_choices": import_source_choices,
            "import_entry_type_choices": [
                {
                    "value": entry_type,
                    "label": SYSTEMS_ENTRY_TYPE_LABELS.get(entry_type, entry_type.replace("_", " ").title()),
                }
                for entry_type in sorted(SUPPORTED_ENTRY_TYPES, key=systems_entry_type_sort_key)
            ],
            "import_run_rows": import_run_rows,
            "import_run_count": len(import_run_rows),
            "supports_dnd5e_import": supports_dnd5e_systems_import(library_slug),
            "permissions": {
                "can_manage_systems": can_manage_campaign_systems(campaign_slug),
                "can_import_shared_systems": bool(user and user.is_admin),
                "can_set_private_visibility": include_private,
                "can_manage_shared_core_entry_edit_permission": bool(user and user.is_admin),
            },
            "links": {
                "flask_systems_lane_url": url_for(
                    "campaign_dm_content_subpage_view",
                    campaign_slug=campaign_slug,
                    dm_content_subpage="systems",
                ),
                "flask_systems_control_url": url_for(
                    "campaign_systems_control_panel_view",
                    campaign_slug=campaign_slug,
                ),
            },
        }

    def normalize_source_ids(value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("source_ids must be an array of source IDs.")
        source_ids = [str(item or "").strip().upper() for item in value]
        source_ids = [item for item in source_ids if item]
        if not source_ids:
            raise ValueError("At least one source ID is required.")
        return source_ids

    def build_systems_index_payload(
        campaign_slug: str,
        *,
        query: str = "",
        reference_query: str = "",
    ) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        systems_service = current_app.extensions["systems_service"]
        source_states = [
            state
            for state in systems_service.list_campaign_source_states(campaign_slug)
            if state.is_enabled and can_access_campaign_systems_source(campaign_slug, state.source.source_id)
        ]
        search_query = query.strip()
        include_source_ids = [state.source.source_id for state in source_states]
        search_results = (
            [
                serialize_systems_entry_summary(entry)
                for entry in filter_accessible_systems_entries(
                    campaign_slug,
                    systems_service.search_entries_for_campaign(
                        campaign_slug,
                        query=search_query,
                        include_source_ids=include_source_ids,
                        limit=None,
                    ),
                    limit=250,
                )
            ]
            if search_query
            else []
        )
        source_cards = []
        for state in source_states:
            rules_reference_entries = filter_accessible_systems_entries(
                campaign_slug,
                systems_service.list_rules_reference_entries_for_campaign(
                    campaign_slug,
                    include_source_ids=[state.source.source_id],
                    limit=None,
                ),
            )
            source_cards.append(
                {
                    **serialize_systems_source_state(campaign_slug, state),
                    "has_rules_reference_entries": bool(rules_reference_entries),
                    "rules_reference_search_scope": systems_service.get_rules_reference_search_scope_for_source(
                        state.source
                    ),
                }
            )
        global_rules_reference_source_ids = [
            row["source_id"]
            for row in source_cards
            if row["has_rules_reference_entries"] and row["rules_reference_search_scope"] == "global"
        ]
        source_scoped_rules_reference_sources = [
            row
            for row in source_cards
            if row["has_rules_reference_entries"] and row["rules_reference_search_scope"] == "source_only"
        ]
        rules_reference_query = reference_query.strip()
        rules_reference_results = (
            [
                serialize_systems_rules_reference_result(entry)
                for entry in filter_accessible_systems_entries(
                    campaign_slug,
                    systems_service.search_rules_reference_entries_for_campaign(
                        campaign_slug,
                        query=rules_reference_query,
                        include_source_ids=global_rules_reference_source_ids,
                        limit=None,
                    ),
                    limit=100,
                )
            ]
            if rules_reference_query
            else []
        )

        return {
            "campaign": serialize_campaign(campaign),
            "library": serialize_systems_library(systems_service.get_campaign_library(campaign_slug)),
            "query": search_query,
            "reference_query": rules_reference_query,
            "sources": source_cards,
            "search_results": search_results,
            "has_rules_reference_search": bool(global_rules_reference_source_ids),
            "rules_reference_results": rules_reference_results,
            "source_scoped_rules_reference_sources": source_scoped_rules_reference_sources,
            "permissions": {
                "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            },
        }

    def get_owned_character_slugs(campaign_slug: str) -> set[str]:
        user = get_current_user()
        if user is None:
            return set()
        assignments = get_auth_store().list_character_assignments_for_user(
            user.id,
            campaign_slug=campaign_slug,
        )
        return {assignment.character_slug for assignment in assignments}

    def require_supported_combat_campaign(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if not supports_combat_tracker(campaign.system):
            raise CampaignCombatValidationError(
                f"Combat tracker support for {campaign.system or 'this system'} is not available yet."
            )
        return campaign

    def build_combat_payload(campaign_slug: str, *, include_sidebar_choices: bool = True) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        can_manage_combat = can_manage_campaign_combat(campaign_slug)
        can_access_dm_content = can_access_campaign_scope(campaign_slug, "dm_content")
        can_access_systems = can_access_campaign_scope(campaign_slug, "systems")
        can_access_characters = can_access_campaign_scope(campaign_slug, "characters")
        can_access_session = can_access_campaign_scope(campaign_slug, "session")
        combat_system_supported = supports_combat_tracker(campaign.system)

        tracker_view: dict[str, Any] = {
            "round_number": 1,
            "current_turn_label": "",
            "has_current_turn": False,
            "combatant_count": 0,
            "combatants": [],
        }
        available_character_choices: list[dict[str, str]] = []
        available_statblock_choices: list[dict[str, str]] = []
        combat_condition_options = list(DND_5E_CONDITION_OPTIONS)
        live_revision = 0
        requested_combatant_id: int | None = None
        selected_combatant: dict[str, Any] | None = None
        selected_player_character: dict[str, Any] | None = None
        player_character_targets: list[dict[str, Any]] = []
        try:
            requested_combatant_id = int(str(request.args.get("combatant") or "").strip())
        except ValueError:
            requested_combatant_id = None

        if combat_system_supported:
            combat_service = current_app.extensions["campaign_combat_service"]
            dm_content_service = current_app.extensions["campaign_dm_content_service"]
            tracker = combat_service.get_tracker(campaign_slug)
            live_revision = tracker.revision
            combatants = combat_service.list_combatants(campaign_slug)
            character_records_by_slug = {}
            for combatant in combatants:
                if not combatant.character_slug:
                    continue
                record = get_character_repository().get_visible_character(campaign_slug, combatant.character_slug)
                if record is not None:
                    character_records_by_slug[combatant.character_slug] = record

            tracker_view = present_combat_tracker(
                tracker,
                combatants,
                combat_service.list_conditions_by_combatant(campaign_slug),
                character_records_by_slug=character_records_by_slug,
                owned_character_slugs=get_owned_character_slugs(campaign_slug),
                can_manage_combat=can_manage_combat,
            )
            combatant_cards = [
                dict(combatant)
                for combatant in list(tracker_view.get("combatants") or [])
                if isinstance(combatant, dict)
            ]
            current_combatant = next(
                (combatant for combatant in combatant_cards if combatant.get("is_current_turn")),
                None,
            )
            if requested_combatant_id is not None:
                selected_combatant = next(
                    (
                        combatant
                        for combatant in combatant_cards
                        if int(combatant.get("id") or 0) == requested_combatant_id
                    ),
                    None,
                )
            if selected_combatant is None:
                selected_combatant = current_combatant or (combatant_cards[0] if combatant_cards else None)

            owned_character_slugs = get_owned_character_slugs(campaign_slug)
            player_character_cards = [
                combatant
                for combatant in combatant_cards
                if str(combatant.get("character_slug") or "").strip()
                and (
                    can_manage_combat
                    or str(combatant.get("character_slug") or "").strip() in owned_character_slugs
                )
            ]
            if requested_combatant_id is not None:
                selected_player_character = next(
                    (
                        combatant
                        for combatant in player_character_cards
                        if int(combatant.get("id") or 0) == requested_combatant_id
                    ),
                    None,
                )
            if selected_player_character is None and selected_combatant is not None:
                selected_combatant_slug = str(selected_combatant.get("character_slug") or "").strip()
                selected_player_character = next(
                    (
                        combatant
                        for combatant in player_character_cards
                        if selected_combatant_slug
                        and str(combatant.get("character_slug") or "").strip() == selected_combatant_slug
                    ),
                    None,
                )
            if selected_player_character is None:
                selected_player_character = next(
                    (combatant for combatant in player_character_cards if combatant.get("is_current_turn")),
                    None,
                ) or (player_character_cards[0] if player_character_cards else None)
            player_character_targets = [
                {
                    "combatant_id": combatant.get("id"),
                    "character_slug": combatant.get("character_slug"),
                    "name": combatant.get("name"),
                    "subtitle": combatant.get("subtitle"),
                    "is_selected": (
                        selected_player_character is not None
                        and combatant.get("id") == selected_player_character.get("id")
                    ),
                    "href": gen2_campaign_href(campaign_slug, f"combat?combatant={combatant.get('id')}"),
                    "flask_href": url_for(
                        "campaign_combat_view",
                        campaign_slug=campaign_slug,
                        combatant=combatant.get("id"),
                    ),
                }
                for combatant in player_character_cards
            ]

            if can_manage_combat and include_sidebar_choices:
                available_character_choices = [
                    {
                        "slug": record.definition.character_slug,
                        "name": record.definition.name,
                        "subtitle": profile_class_level_text(record.definition.profile).strip(),
                        "initiative_bonus": str(int(record.definition.stats.get("initiative_bonus") or 0)),
                    }
                    for record in combat_service.list_available_player_characters(campaign_slug)
                ]

                if can_access_dm_content:
                    available_statblock_choices = [
                        {
                            "id": str(statblock.id),
                            "title": statblock.title,
                            "subtitle": f"HP {statblock.max_hp} - Speed {statblock.speed_text}",
                            "initiative_bonus": (
                                f"+{statblock.initiative_bonus}"
                                if statblock.initiative_bonus > 0
                                else str(statblock.initiative_bonus)
                            ),
                        }
                        for statblock in dm_content_service.list_statblocks(campaign_slug)
                    ]

            combat_condition_options = sorted(
                {
                    *DND_5E_CONDITION_OPTIONS,
                    *[
                        definition.name
                        for definition in dm_content_service.list_condition_definitions(campaign_slug)
                    ],
                }
            )

        selected_combatant_id = (
            int(selected_combatant.get("id"))
            if selected_combatant is not None and selected_combatant.get("id") is not None
            else None
        )
        live_view_token = build_combat_live_view_token(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
        )

        return {
            "campaign": serialize_campaign(campaign),
            "combat_system_supported": combat_system_supported,
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "tracker": tracker_view,
            "selected_combatant_id": selected_combatant_id,
            "selected_combatant": selected_combatant,
            "selected_player_character": selected_player_character,
            "player_character_targets": player_character_targets,
            "available_character_choices": available_character_choices,
            "available_statblock_choices": available_statblock_choices,
            "combat_condition_options": combat_condition_options,
            "poll_settings": {
                "active_interval_ms": 500,
                "idle_interval_ms": 3000,
                "idle_threshold_ms": 30000,
            },
            "links": {
                "flask_combat_url": url_for("campaign_combat_view", campaign_slug=campaign_slug),
                "flask_campaign_url": url_for("campaign_view", campaign_slug=campaign_slug),
                "flask_characters_url": (
                    url_for("character_roster_view", campaign_slug=campaign_slug)
                    if can_access_characters
                    else ""
                ),
                "flask_session_url": (
                    url_for("campaign_session_view", campaign_slug=campaign_slug)
                    if can_access_session
                    else ""
                ),
                "flask_dm_status_url": (
                    url_for("campaign_combat_dm_view", campaign_slug=campaign_slug)
                    if can_manage_combat
                    else ""
                ),
                "flask_dm_controls_url": (
                    url_for("campaign_combat_dm_view", campaign_slug=campaign_slug, view="controls")
                    if can_manage_combat
                    else ""
                ),
                "flask_status_url": (
                    url_for("campaign_combat_status_view", campaign_slug=campaign_slug)
                    if can_manage_combat
                    else ""
                ),
            },
            "permissions": {
                "can_manage_combat": can_manage_combat,
                "can_access_dm_content": can_access_dm_content,
                "can_access_systems": can_access_systems,
            },
        }

    def serialize_character_state(state_record: CharacterStateRecord) -> dict[str, Any]:
        return {
            "campaign_slug": state_record.campaign_slug,
            "character_slug": state_record.character_slug,
            "revision": state_record.revision,
            "state": state_record.state,
            "updated_at": serialize_datetime(state_record.updated_at),
            "updated_by_user_id": state_record.updated_by_user_id,
        }

    def build_character_portrait_asset_ref(character_slug: str, filename: str) -> str:
        extension = Path(filename).suffix.lower()
        return f"characters/{character_slug}/portrait{extension}"

    def validate_character_portrait_payload(payload: dict[str, Any]) -> dict[str, Any]:
        portrait_file = decode_embedded_file(payload.get("portrait_file"), label="portrait_file")
        filename = Path(str(portrait_file["filename"] or "").strip()).name
        if not filename:
            raise ValueError("Choose an image file before saving the portrait.")
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS:
            raise ValueError("Character portraits must be PNG, JPG, GIF, or WEBP files.")
        data_blob = portrait_file["data_blob"]
        if not data_blob:
            raise ValueError("Uploaded portrait files cannot be empty.")
        if len(data_blob) > CHARACTER_PORTRAIT_MAX_BYTES:
            raise ValueError("Character portraits must stay under 8 MB.")
        alt_text = str(payload.get("alt_text") or "").strip()
        caption = str(payload.get("caption") or "").strip()
        if len(alt_text) > CHARACTER_PORTRAIT_ALT_MAX_LENGTH:
            raise ValueError(f"Portrait alt text must stay under {CHARACTER_PORTRAIT_ALT_MAX_LENGTH} characters.")
        if len(caption) > CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH:
            raise ValueError(f"Portrait captions must stay under {CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH} characters.")
        return {
            "filename": filename,
            "data_blob": data_blob,
            "alt_text": alt_text,
            "caption": caption,
        }

    def update_character_portrait_profile(
        definition,
        *,
        asset_ref: str = "",
        alt_text: str = "",
        caption: str = "",
    ):
        definition_payload = definition.to_dict()
        profile = dict(definition_payload.get("profile") or {})
        clean_asset_ref = str(asset_ref or "").strip()
        if clean_asset_ref:
            profile["portrait_asset_ref"] = clean_asset_ref
            profile["portrait_alt"] = str(alt_text or "").strip()
            profile["portrait_caption"] = str(caption or "").strip()
        else:
            profile.pop("portrait_asset_ref", None)
            profile.pop("portrait_alt", None)
            profile.pop("portrait_caption", None)
        definition_payload["profile"] = profile
        return definition.__class__.from_dict(definition_payload)

    def build_character_portrait_payload(campaign, record: CharacterRecord) -> dict[str, Any] | None:
        profile = dict(record.definition.profile or {})
        asset_ref = str(profile.get("portrait_asset_ref") or "").strip()
        if not asset_ref:
            return None
        try:
            asset_record = get_campaign_asset_file_record(campaign, asset_ref)
        except CampaignContentError:
            return None
        if asset_record is None:
            return None
        return {
            "asset_ref": asset_record.asset_ref,
            "url": url_for(
                "character_portrait_asset",
                campaign_slug=campaign.slug,
                character_slug=record.definition.character_slug,
            ),
            "media_type": asset_record.media_type,
            "alt_text": str(profile.get("portrait_alt") or record.definition.name).strip()
            or record.definition.name,
            "caption": str(profile.get("portrait_caption") or "").strip(),
        }

    def serialize_character_roster_tools(campaign_slug: str, campaign) -> dict[str, Any]:
        campaign_system = getattr(campaign, "system", "")
        can_manage = can_manage_campaign_session(campaign_slug)
        create_lane = native_character_create_lane(campaign_system)
        can_create = can_manage and supports_native_character_create(campaign_system)
        return {
            "can_create_characters": can_create,
            "can_import_xianxia_characters": can_create and create_lane == CHARACTER_ROUTE_LANE_XIANXIA,
            "native_character_tools_supported": supports_native_character_tools(campaign_system),
            "native_character_create_supported": supports_native_character_create(campaign_system),
            "character_create_lane": create_lane,
        }

    def serialize_character_roster_links(campaign_slug: str, campaign) -> dict[str, str]:
        tools = serialize_character_roster_tools(campaign_slug, campaign)
        encoded_campaign_slug = campaign_slug
        links = {
            "flask_roster_url": url_for("character_roster_view", campaign_slug=campaign_slug),
            "gen2_roster_url": f"/app-next/campaigns/{encoded_campaign_slug}/characters",
        }
        if tools["can_create_characters"]:
            links["flask_create_character_url"] = url_for("character_create_view", campaign_slug=campaign_slug)
            links["create_character_url"] = f"/app-next/campaigns/{encoded_campaign_slug}/characters/new"
        if tools["can_import_xianxia_characters"]:
            links["flask_import_xianxia_url"] = url_for(
                "character_import_xianxia_manual_view",
                campaign_slug=campaign_slug,
            )
            links["import_xianxia_url"] = (
                f"/app-next/campaigns/{encoded_campaign_slug}/characters/import/xianxia-manual"
            )
        return links

    def list_builder_campaign_page_records(campaign_slug: str, campaign) -> list[object]:
        return list_builder_campaign_page_records_for_store(
            get_campaign_page_store(),
            campaign_slug,
            campaign,
            relevant_sections={CAMPAIGN_MECHANICS_SECTION, CAMPAIGN_ITEMS_SECTION},
        )

    def make_json_safe(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): make_json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [make_json_safe(item) for item in value]
        if hasattr(value, "to_dict"):
            return make_json_safe(value.to_dict())
        if hasattr(value, "__dict__"):
            return make_json_safe(
                {
                    key: item
                    for key, item in vars(value).items()
                    if not str(key).startswith("_")
                }
            )
        return str(value)

    def normalize_character_authoring_values(payload: dict[str, Any]) -> dict[str, Any]:
        raw_values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
        values: dict[str, Any] = {}
        for key, value in dict(raw_values or {}).items():
            if isinstance(value, list):
                values[str(key)] = [str(item or "") for item in value]
            elif value is None:
                values[str(key)] = ""
            else:
                values[str(key)] = str(value)
        return values

    def serialize_character_authoring_links(campaign_slug: str, campaign) -> dict[str, str]:
        links = serialize_character_roster_links(campaign_slug, campaign)
        links["flask_create_url"] = url_for("character_create_view", campaign_slug=campaign_slug)
        links["gen2_create_url"] = f"/app-next/campaigns/{campaign_slug}/characters/new"
        if native_character_create_lane(getattr(campaign, "system", "")) == CHARACTER_ROUTE_LANE_XIANXIA:
            links["flask_import_xianxia_url"] = url_for(
                "character_import_xianxia_manual_view",
                campaign_slug=campaign_slug,
            )
            links["gen2_import_xianxia_url"] = (
                f"/app-next/campaigns/{campaign_slug}/characters/import/xianxia-manual"
            )
        return links

    def ensure_character_authoring_access(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if get_current_user() is None:
            return campaign, json_error("Authentication required.", 401, code="auth_required")
        if not can_access_campaign_scope(campaign_slug, "characters") or not can_manage_campaign_session(
            campaign_slug
        ):
            return campaign, json_error(
                "You do not have permission to create characters in this campaign.",
                403,
                code="forbidden",
            )
        if not supports_native_character_create(getattr(campaign, "system", "")):
            return campaign, json_error(
                native_character_create_unsupported_message(getattr(campaign, "system", "")),
                400,
                code="unsupported_campaign_system",
            )
        return campaign, None

    def serialize_dnd_character_create_context(
        campaign_slug: str,
        campaign,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        builder_context = build_level_one_builder_context(
            current_app.extensions["systems_service"],
            campaign_slug,
            values or {},
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )
        builder_ready = bool(
            builder_context.get("class_options")
            and builder_context.get("species_options")
            and builder_context.get("background_options")
        )
        return {
            "lane": CHARACTER_ROUTE_LANE_DND5E,
            "builder_ready": builder_ready,
            "values": make_json_safe(builder_context.get("values") or {}),
            "class_options": make_json_safe(builder_context.get("class_options") or []),
            "species_options": make_json_safe(builder_context.get("species_options") or []),
            "background_options": make_json_safe(builder_context.get("background_options") or []),
            "subclass_options": make_json_safe(builder_context.get("subclass_options") or []),
            "requires_subclass": bool(builder_context.get("requires_subclass")),
            "choice_sections": make_json_safe(builder_context.get("choice_sections") or []),
            "preview": make_json_safe(builder_context.get("preview") or {}),
            "limitations": make_json_safe(builder_context.get("limitations") or []),
        }

    def serialize_xianxia_character_create_context(
        campaign_slug: str,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        create_context = build_xianxia_character_create_context(
            values or {},
            systems_service=current_app.extensions["systems_service"],
            campaign_slug=campaign_slug,
        )
        return {
            "lane": CHARACTER_ROUTE_LANE_XIANXIA,
            "values": make_json_safe(create_context.get("values") or {}),
            "attribute_fields": make_json_safe(create_context.get("attribute_fields") or []),
            "effort_fields": make_json_safe(create_context.get("effort_fields") or []),
            "energy_fields": make_json_safe(create_context.get("energy_fields") or []),
            "trained_skill_fields": make_json_safe(create_context.get("trained_skill_fields") or []),
            "martial_art_fields": make_json_safe(create_context.get("martial_art_fields") or []),
            "martial_art_options": make_json_safe(create_context.get("martial_art_options") or []),
            "martial_art_rank_choices": make_json_safe(create_context.get("martial_art_rank_choices") or []),
            "manual_armor_field": make_json_safe(create_context.get("manual_armor_field") or {}),
            "dao_field": make_json_safe(create_context.get("dao_field") or {}),
            "generic_technique_options": make_json_safe(create_context.get("generic_technique_options") or []),
            "gm_granted_generic_technique_input": XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT,
            "defaults": make_json_safe(create_context.get("defaults") or {}),
        }

    def build_character_create_payload(
        campaign_slug: str,
        campaign,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lane = native_character_create_lane(getattr(campaign, "system", ""))
        if lane == CHARACTER_ROUTE_LANE_DND5E:
            create_context = serialize_dnd_character_create_context(campaign_slug, campaign, values)
        elif lane == CHARACTER_ROUTE_LANE_XIANXIA:
            create_context = serialize_xianxia_character_create_context(campaign_slug, values)
        else:
            create_context = {"lane": lane, "builder_ready": False}
        return {
            "ok": True,
            "campaign": serialize_campaign(campaign),
            "lane": lane,
            "tools": serialize_character_roster_tools(campaign_slug, campaign),
            "links": serialize_character_authoring_links(campaign_slug, campaign),
            "create": create_context,
        }

    def write_new_character_record(campaign_slug: str, definition, import_metadata, initial_state: dict[str, Any]):
        config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / definition.character_slug
        definition_path = character_dir / "definition.yaml"
        import_path = character_dir / "import.yaml"
        if definition_path.exists() or import_path.exists():
            raise FileExistsError(
                f"A character with slug '{definition.character_slug}' already exists in this campaign."
            )
        write_yaml(definition_path, definition.to_dict())
        write_yaml(import_path, import_metadata.to_dict())
        current_app.extensions["character_state_store"].initialize_state_if_missing(
            definition,
            initial_state,
        )
        return load_character_record(campaign_slug, definition.character_slug)

    def build_xianxia_manual_import_martial_art_rows(values: dict[str, Any]) -> list[dict[str, object]]:
        row_numbers: set[int] = set()
        for key in values:
            match = re.match(
                r"^martial_art_(\d+)_(slug|name|rank|teacher|breakthrough|notes)$",
                str(key),
            )
            if match:
                row_numbers.add(int(match.group(1)))
        row_count = max(max(row_numbers, default=0), 3)
        return [
            {
                "index": index,
                "slug_input_name": f"martial_art_{index}_slug",
                "name_input_name": f"martial_art_{index}_name",
                "rank_input_name": f"martial_art_{index}_rank",
                "teacher_input_name": f"martial_art_{index}_teacher",
                "breakthrough_input_name": f"martial_art_{index}_breakthrough",
                "notes_input_name": f"martial_art_{index}_notes",
                "selected_slug": values.get(f"martial_art_{index}_slug", ""),
                "name": values.get(f"martial_art_{index}_name", ""),
                "rank": values.get(f"martial_art_{index}_rank", ""),
                "teacher": values.get(f"martial_art_{index}_teacher", ""),
                "breakthrough": values.get(f"martial_art_{index}_breakthrough", ""),
                "notes": values.get(f"martial_art_{index}_notes", ""),
            }
            for index in range(1, row_count + 1)
        ]

    def build_xianxia_manual_import_context(
        campaign_slug: str,
        values: dict[str, Any] | None = None,
        *,
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_values = normalize_character_authoring_values({"values": values or {}})
        martial_art_options = list_xianxia_manual_import_martial_art_options(
            systems_service=current_app.extensions["systems_service"],
            campaign_slug=campaign_slug,
        )
        return {
            "values": normalized_values,
            "realm_choices": ("Mortal", "Immortal", "Divine"),
            "honor_choices": ("Venerable", "Majestic", "Honorable", "Disgraced", "Demonic"),
            "martial_art_rank_choices": list(XIANXIA_MARTIAL_ART_IMPORT_RANKS),
            "martial_art_rows": build_xianxia_manual_import_martial_art_rows(normalized_values),
            "attribute_fields": [
                {
                    "key": key,
                    "label": XIANXIA_ATTRIBUTE_LABELS[key],
                    "input_name": f"attribute_{key}",
                    "value": normalized_values.get(f"attribute_{key}", "0"),
                }
                for key in XIANXIA_ATTRIBUTE_KEYS
            ],
            "effort_fields": [
                {
                    "key": key,
                    "label": XIANXIA_EFFORT_LABELS[key],
                    "input_name": f"effort_{key}",
                    "value": normalized_values.get(f"effort_{key}", "0"),
                }
                for key in XIANXIA_EFFORT_KEYS
            ],
            "energy_fields": [
                {
                    "key": key,
                    "label": key.title(),
                    "max_input_name": f"energy_{key}_max",
                    "max_value": normalized_values.get(f"energy_{key}_max", "0"),
                }
                for key in XIANXIA_ENERGY_KEYS
            ],
            "martial_art_options": make_json_safe(martial_art_options),
            "preview": preview,
        }

    def build_xianxia_manual_import_payload(values: dict[str, Any]) -> dict[str, Any]:
        ignored_inputs = {"active_stance", "active_aura"}
        normalized_values = {
            key: str(value or "")
            for key, value in dict(values or {}).items()
            if key not in ignored_inputs
        }
        payload: dict[str, Any] = dict(normalized_values)
        payload["energy_maxima"] = {
            key: normalized_values.get(f"energy_{key}_max", "")
            for key in XIANXIA_ENERGY_KEYS
        }
        payload["state"] = {
            "xianxia": {
                "currency": {
                    "coin": normalized_values.get("coin", ""),
                    "supply": normalized_values.get("supply", ""),
                    "spirit_stones": normalized_values.get("spirit_stones", ""),
                },
                "notes": {
                    "player_notes_markdown": normalized_values.get("player_notes_markdown", ""),
                },
            },
        }
        return payload

    def build_xianxia_manual_import_preview(definition, initial_state: dict[str, Any]) -> dict[str, Any]:
        xianxia = dict(getattr(definition, "xianxia", {}) or {})
        state_xianxia = dict(initial_state.get("xianxia") or {})
        inventory = dict(state_xianxia.get("inventory") or {})
        return {
            "name": definition.name,
            "slug": definition.character_slug,
            "realm": xianxia.get("realm"),
            "actions_per_turn": xianxia.get("actions_per_turn"),
            "trained_skill_count": len(list(dict(xianxia.get("skills") or {}).get("trained") or [])),
            "martial_art_count": len(list(xianxia.get("martial_arts") or [])),
            "inventory_count": len(list(inventory.get("quantities") or [])),
            "hp": dict(state_xianxia.get("vitals") or {}).get("current_hp"),
            "hp_max": dict(xianxia.get("durability") or {}).get("hp_max"),
            "stance": dict(state_xianxia.get("vitals") or {}).get("current_stance"),
            "stance_max": dict(xianxia.get("durability") or {}).get("stance_max"),
        }

    def serialize_character_links(campaign_slug: str, campaign, record: CharacterRecord) -> dict[str, str]:
        character_slug = record.definition.character_slug
        campaign_system = getattr(campaign, "system", "")
        links = {
            "flask_roster_url": url_for("character_roster_view", campaign_slug=campaign_slug),
            "flask_character_url": url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            ),
        }
        if (
            can_access_campaign_scope(campaign_slug, "characters")
            and has_session_mode_access(campaign_slug, character_slug)
            and supports_native_character_tools(campaign_system)
            and supports_native_character_tools(getattr(record.definition, "system", ""))
        ):
            links["advanced_editor_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/edit",
            )
            links["flask_advanced_editor_url"] = url_for(
                "character_edit_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
            retraining_availability = character_retraining_availability(campaign_slug, campaign, record)
            if str(retraining_availability.get("status") or "").strip() == "ready":
                links["retraining_url"] = gen2_campaign_href(
                    campaign_slug,
                    f"characters/{character_slug}/retraining",
                )
                links["flask_retraining_url"] = url_for(
                    "character_retraining_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
        can_level_up_character = has_session_mode_access(campaign_slug, character_slug)
        can_manage_character = can_manage_campaign_session(campaign_slug)
        if (
            can_level_up_character
            and character_advancement_lane(campaign_system) == CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP
            and supports_native_character_tools(getattr(record.definition, "system", ""))
        ):
            level_up_readiness = native_level_up_readiness(
                current_app.extensions["systems_service"],
                campaign_slug,
                record.definition,
                campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
            )
            readiness_status = str(level_up_readiness.get("status") or "").strip()
            if readiness_status == "ready":
                links["level_up_url"] = gen2_campaign_href(
                    campaign_slug,
                    f"characters/{character_slug}/level-up",
                )
                links["flask_level_up_url"] = url_for(
                    "character_level_up_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            elif readiness_status == "repairable" and can_manage_character:
                links["progression_repair_url"] = gen2_campaign_href(
                    campaign_slug,
                    f"characters/{character_slug}/progression-repair",
                )
                links["flask_progression_repair_url"] = url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
        if (
            can_access_campaign_scope(campaign_slug, "characters")
            and can_manage_campaign_session(campaign_slug)
            and character_advancement_lane(campaign_system) == CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
        ):
            links["cultivation_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/cultivation",
            )
            links["flask_cultivation_url"] = url_for(
                "character_xianxia_cultivation_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        return links

    def normalize_character_editor_values(payload: dict[str, Any]) -> dict[str, str]:
        raw_values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
        values: dict[str, str] = {}
        for key, value in dict(raw_values or {}).items():
            field_name = str(key or "").strip()
            if not field_name:
                continue
            if isinstance(value, list):
                values[field_name] = str(value[-1] if value else "")
            elif value is None:
                values[field_name] = ""
            else:
                values[field_name] = str(value)
        return values

    def character_advanced_editor_is_supported(campaign, record: CharacterRecord) -> bool:
        return bool(
            supports_native_character_tools(getattr(campaign, "system", ""))
            and supports_native_character_tools(getattr(record.definition, "system", ""))
        )

    def build_character_advanced_editor_parts(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        form_values: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], list[object], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        level_up_readiness = native_level_up_readiness(
            current_app.extensions["systems_service"],
            campaign_slug,
            record.definition,
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )
        linked_feature_authoring = build_linked_feature_authoring_support(
            record.definition,
            readiness=level_up_readiness,
        )
        campaign_page_records = [
            page_record
            for page_record in get_campaign_page_store().list_page_records(campaign_slug)
            if page_record.page.published
            and page_record.page.reveal_after_session <= campaign.current_session
            and str(page_record.page.section or "").strip() != "Sessions"
        ]
        spell_catalog = _build_spell_catalog(
            _list_campaign_enabled_entries(
                current_app.extensions["systems_service"],
                campaign_slug,
                "spell",
            )
        )
        optionalfeature_catalog = {
            str(entry.slug or "").strip(): entry
            for entry in _list_campaign_enabled_entries(
                current_app.extensions["systems_service"],
                campaign_slug,
                "optionalfeature",
            )
            if str(entry.slug or "").strip()
        }
        item_catalog = build_character_item_catalog(campaign_slug)
        edit_context = build_native_character_edit_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values,
            state_notes=dict((record.state_record.state or {}).get("notes") or {}),
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
            item_catalog=item_catalog,
            linked_feature_authoring_support=linked_feature_authoring,
        )
        edit_context["state_revision"] = record.state_record.revision
        return (
            edit_context,
            campaign_page_records,
            optionalfeature_catalog,
            spell_catalog,
            item_catalog,
            linked_feature_authoring,
        )

    def serialize_character_advanced_editor_response(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        edit_context: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        supported = character_advanced_editor_is_supported(campaign, record)
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "character": serialize_character_record(campaign_slug, record),
                "lane": "dnd5e" if supported else "unsupported",
                "supported": supported,
                "message": message,
                "unsupported_message": (
                    ""
                    if supported
                    else "Advanced Editor is currently available only for DND-5E native character tools in Gen2."
                ),
                "editor": make_json_safe(edit_context) if edit_context is not None else None,
                "links": {
                    **serialize_character_links(campaign_slug, campaign, record),
                    "character_url": gen2_campaign_href(
                        campaign_slug,
                        f"characters/{record.definition.character_slug}",
                    ),
                    "flask_character_url": url_for(
                        "character_read_view",
                        campaign_slug=campaign_slug,
                        character_slug=record.definition.character_slug,
                    ),
                },
            }
        )

    def load_character_advanced_editor_target(campaign_slug: str, character_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return campaign, record, json_error(
                "You do not have permission to edit this character.",
                403,
                code="forbidden",
            )
        return campaign, record, None

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_advanced_editor_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_advanced_editor_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        if not character_advanced_editor_is_supported(campaign, record):
            return serialize_character_advanced_editor_response(campaign_slug, campaign, record)

        edit_context, *_ = build_character_advanced_editor_parts(
            campaign_slug,
            campaign,
            record,
        )
        return serialize_character_advanced_editor_response(
            campaign_slug,
            campaign,
            record,
            edit_context=edit_context,
        )

    @api.put("/campaigns/<campaign_slug>/characters/<character_slug>/advanced-editor")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_advanced_editor_update(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_advanced_editor_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        if not character_advanced_editor_is_supported(campaign, record):
            return json_error(
                "Advanced Editor is currently available only for DND-5E native character tools in Gen2.",
                400,
                code="unsupported_campaign_system",
            )

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            form_values = normalize_character_editor_values(payload)
            (
                _edit_context,
                campaign_page_records,
                optionalfeature_catalog,
                spell_catalog,
                item_catalog,
                linked_feature_authoring,
            ) = build_character_advanced_editor_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            definition, import_metadata, inventory_quantity_overrides = apply_native_character_edits(
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
            )
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            removed_resource_ids: set[str] = set()
            source_type = str((record.definition.source or {}).get("source_type") or "").strip()
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
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                inventory_quantity_overrides=inventory_quantity_overrides,
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
                notes_payload["background_markdown"] = str(form_values.get("background_markdown") or "")
                merged_state["notes"] = notes_payload
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            return json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CharacterEditValidationError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refreshed_record = load_character_record(campaign_slug, character_slug)
        edit_context, *_ = build_character_advanced_editor_parts(
            campaign_slug,
            campaign,
            refreshed_record,
        )
        return serialize_character_advanced_editor_response(
            campaign_slug,
            campaign,
            refreshed_record,
            edit_context=edit_context,
            message="Character details updated.",
        )

    def normalize_character_retraining_values(payload: dict[str, Any]) -> dict[str, str]:
        raw_values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
        values: dict[str, str] = {}
        for key, value in dict(raw_values or {}).items():
            field_name = str(key or "").strip()
            if not field_name:
                continue
            if isinstance(value, list):
                values[field_name] = str(value[-1] if value else "")
            elif value is None:
                values[field_name] = ""
            else:
                values[field_name] = str(value)
        return values

    def character_retraining_base_readiness(campaign_slug: str, campaign, record: CharacterRecord) -> dict[str, Any]:
        campaign_system = getattr(campaign, "system", "")
        if not supports_native_character_tools(campaign_system):
            return {
                "status": "unsupported",
                "message": character_advancement_unsupported_message(campaign_system),
            }
        if not supports_native_character_tools(getattr(record.definition, "system", "")):
            return {
                "status": "unsupported",
                "message": "Retraining is currently available only for DND-5E native character tools in Gen2.",
            }
        level_up_readiness = native_level_up_readiness(
            current_app.extensions["systems_service"],
            campaign_slug,
            record.definition,
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )
        linked_feature_authoring = build_linked_feature_authoring_support(
            record.definition,
            readiness=level_up_readiness,
        )
        if not bool(linked_feature_authoring.get("supported")):
            readiness_status = str(level_up_readiness.get("status") or "").strip()
            return {
                "status": "repairable" if readiness_status == "repairable" else "unsupported",
                "message": str(linked_feature_authoring.get("message") or "This character cannot use retraining yet."),
                "level_up_readiness": level_up_readiness,
                "linked_feature_authoring": linked_feature_authoring,
            }
        return {
            "status": "candidate",
            "message": "",
            "level_up_readiness": level_up_readiness,
            "linked_feature_authoring": linked_feature_authoring,
        }

    def character_retraining_catalog_parts(campaign_slug: str, campaign) -> tuple[list[object], dict[str, Any], dict[str, Any], dict[str, Any]]:
        campaign_page_records = [
            page_record
            for page_record in get_campaign_page_store().list_page_records(campaign_slug)
            if page_record.page.published
            and page_record.page.reveal_after_session <= campaign.current_session
            and str(page_record.page.section or "").strip() != "Sessions"
        ]
        spell_catalog = _build_spell_catalog(
            _list_campaign_enabled_entries(
                current_app.extensions["systems_service"],
                campaign_slug,
                "spell",
            )
        )
        optionalfeature_catalog = {
            str(entry.slug or "").strip(): entry
            for entry in _list_campaign_enabled_entries(
                current_app.extensions["systems_service"],
                campaign_slug,
                "optionalfeature",
            )
            if str(entry.slug or "").strip()
        }
        item_catalog = build_character_item_catalog(campaign_slug)
        return campaign_page_records, optionalfeature_catalog, spell_catalog, item_catalog

    def build_character_retraining_context_parts(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        form_values: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], list[object], dict[str, Any], dict[str, Any], dict[str, Any]]:
        campaign_page_records, optionalfeature_catalog, spell_catalog, item_catalog = character_retraining_catalog_parts(
            campaign_slug,
            campaign,
        )
        retraining_context = build_native_character_retraining_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values,
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
            item_catalog=item_catalog,
        )
        retraining_context["state_revision"] = record.state_record.revision
        return retraining_context, campaign_page_records, optionalfeature_catalog, spell_catalog, item_catalog

    def character_retraining_availability(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        form_values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        readiness = character_retraining_base_readiness(campaign_slug, campaign, record)
        if str(readiness.get("status") or "").strip() != "candidate":
            return readiness
        try:
            retraining_context, *_ = build_character_retraining_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
        except (CharacterEditValidationError, ValueError) as exc:
            return {
                **readiness,
                "status": "unsupported",
                "message": str(exc),
            }
        if not list(retraining_context.get("feature_rows") or []):
            return {
                **readiness,
                "status": "empty",
                "message": "This character does not currently have any supported structured retraining options.",
                "retraining_context": retraining_context,
            }
        return {
            **readiness,
            "status": "ready",
            "message": "",
            "retraining_context": retraining_context,
        }

    def character_retraining_is_supported(readiness: dict[str, Any]) -> bool:
        return str(readiness.get("status") or "").strip() == "ready"

    def serialize_character_retraining_context(retraining_context: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "state_revision",
            "values",
            "feature_rows",
            "supported_scope",
        )
        return {key: make_json_safe(retraining_context.get(key)) for key in keys}

    def character_retraining_links(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        readiness: dict[str, Any],
    ) -> dict[str, str]:
        character_slug = record.definition.character_slug
        links = {
            **serialize_character_links(campaign_slug, campaign, record),
            "character_url": gen2_campaign_href(campaign_slug, f"characters/{character_slug}"),
            "flask_character_url": url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            ),
        }
        if character_advanced_editor_is_supported(campaign, record):
            links["advanced_editor_url"] = gen2_campaign_href(campaign_slug, f"characters/{character_slug}/edit")
            links["flask_advanced_editor_url"] = url_for(
                "character_edit_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        readiness_status = str(readiness.get("status") or "").strip()
        nested_level_up_status = str(
            dict(readiness.get("level_up_readiness") or {}).get("status") or ""
        ).strip()
        if readiness_status != "repairable" and nested_level_up_status == "repairable":
            readiness_status = "repairable"
        if readiness_status == "ready":
            links["retraining_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/retraining",
            )
            links["flask_retraining_url"] = url_for(
                "character_retraining_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        elif readiness_status == "repairable":
            links["progression_repair_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/progression-repair",
            )
            links["flask_progression_repair_url"] = url_for(
                "character_progression_repair_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        return links

    def serialize_character_retraining_response(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        readiness: dict[str, Any] | None = None,
        retraining_context: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        readiness = readiness or character_retraining_availability(campaign_slug, campaign, record)
        if retraining_context is None:
            retraining_context = dict(readiness.get("retraining_context") or {}) or None
        readiness_status = str(readiness.get("status") or "").strip() or "unsupported"
        nested_level_up_status = str(
            dict(readiness.get("level_up_readiness") or {}).get("status") or ""
        ).strip()
        if readiness_status != "repairable" and nested_level_up_status == "repairable":
            readiness_status = "repairable"
        supported = character_retraining_is_supported(readiness)
        lane = "dnd5e" if supported else ("repairable" if readiness_status == "repairable" else "unsupported")
        unsupported_message = "" if supported else str(
            readiness.get("message") or "This character is not ready for Gen2 retraining."
        )
        serialized_readiness = {
            key: value
            for key, value in dict(readiness or {}).items()
            if key != "retraining_context"
        }
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "character": serialize_character_record(campaign_slug, record),
                "lane": lane,
                "supported": supported,
                "message": message,
                "unsupported_message": unsupported_message,
                "readiness": make_json_safe(serialized_readiness),
                "retraining": (
                    serialize_character_retraining_context(retraining_context)
                    if retraining_context is not None and supported
                    else None
                ),
                "links": character_retraining_links(campaign_slug, campaign, record, readiness),
            }
        )

    def load_character_retraining_target(campaign_slug: str, character_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return campaign, record, json_error(
                "You do not have permission to retrain this character.",
                403,
                code="forbidden",
            )
        return campaign, record, None

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/retraining")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_retraining_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_retraining_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        form_values = normalize_character_retraining_values(dict(request.args))
        readiness = character_retraining_availability(
            campaign_slug,
            campaign,
            record,
            form_values=form_values,
        )
        return serialize_character_retraining_response(campaign_slug, campaign, record, readiness=readiness)

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/retraining")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_retraining_submit(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_retraining_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        readiness = character_retraining_availability(campaign_slug, campaign, record)
        if not character_retraining_is_supported(readiness):
            return json_error(
                str(readiness.get("message") or "This character is not ready for Gen2 retraining."),
                400,
                code="unsupported_campaign_system",
            )
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            form_values = normalize_character_retraining_values(payload)
            (
                _retraining_context,
                campaign_page_records,
                optionalfeature_catalog,
                spell_catalog,
                item_catalog,
            ) = build_character_retraining_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            definition, import_metadata, inventory_quantity_overrides = apply_native_character_retraining(
                campaign_slug,
                record.definition,
                record.import_metadata,
                campaign_page_records=campaign_page_records,
                form_values=form_values,
                optionalfeature_catalog=optionalfeature_catalog,
                spell_catalog=spell_catalog,
                item_catalog=item_catalog,
                systems_service=current_app.extensions["systems_service"],
            )
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            removed_resource_ids: set[str] = set()
            source_type = str((record.definition.source or {}).get("source_type") or "").strip()
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
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                inventory_quantity_overrides=inventory_quantity_overrides,
                removed_resource_ids=removed_resource_ids,
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            return json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CharacterEditValidationError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refreshed_record = load_character_record(campaign_slug, character_slug)
        refreshed_readiness = character_retraining_availability(campaign_slug, campaign, refreshed_record)
        return serialize_character_retraining_response(
            campaign_slug,
            campaign,
            refreshed_record,
            readiness=refreshed_readiness,
            message="Retraining saved.",
        )

    def normalize_character_level_up_values(payload: dict[str, Any]) -> dict[str, str]:
        raw_values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
        values: dict[str, str] = {}
        for key, value in dict(raw_values or {}).items():
            field_name = str(key or "").strip()
            if not field_name:
                continue
            if isinstance(value, list):
                values[field_name] = str(value[-1] if value else "")
            elif value is None:
                values[field_name] = ""
            else:
                values[field_name] = str(value)
        return values

    def character_level_up_readiness(campaign_slug: str, campaign, record: CharacterRecord) -> dict[str, Any]:
        campaign_system = getattr(campaign, "system", "")
        if character_advancement_lane(campaign_system) != CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP:
            return {
                "status": "unsupported",
                "message": character_advancement_unsupported_message(campaign_system),
            }
        if not supports_native_character_tools(getattr(record.definition, "system", "")):
            return {
                "status": "unsupported",
                "message": "Level-up is currently available only for DND-5E native character tools in Gen2.",
            }
        return native_level_up_readiness(
            current_app.extensions["systems_service"],
            campaign_slug,
            record.definition,
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )

    def character_level_up_is_supported(readiness: dict[str, Any]) -> bool:
        return str(readiness.get("status") or "").strip() == "ready"

    def serialize_character_level_up_context(level_up_context: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "state_revision",
            "values",
            "character_name",
            "current_level",
            "next_level",
            "advancement_mode",
            "mode_options",
            "can_add_class",
            "current_class_rows",
            "target_row_options",
            "target_class_row_id",
            "row_current_level",
            "row_target_level",
            "new_class_options",
            "new_subclass_options",
            "multiclass_requirement_text",
            "multiclass_requirements_met",
            "subclass_options",
            "requires_subclass",
            "choice_sections",
            "limitations",
            "preview",
            "field_live_preview",
            "preview_region_ids",
            "live_region_ids",
        )
        return {key: make_json_safe(level_up_context.get(key)) for key in keys}

    def build_character_level_up_context_parts(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        form_values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        level_up_context = build_native_level_up_context(
            current_app.extensions["systems_service"],
            campaign_slug,
            record.definition,
            form_values or {},
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )
        level_up_context["state_revision"] = record.state_record.revision
        return level_up_context

    def character_level_up_links(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        readiness: dict[str, Any],
    ) -> dict[str, str]:
        character_slug = record.definition.character_slug
        links = {
            **serialize_character_links(campaign_slug, campaign, record),
            "character_url": gen2_campaign_href(campaign_slug, f"characters/{character_slug}"),
            "flask_character_url": url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            ),
        }
        readiness_status = str(readiness.get("status") or "").strip()
        if readiness_status == "ready":
            links["level_up_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/level-up",
            )
            links["flask_level_up_url"] = url_for(
                "character_level_up_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        elif readiness_status == "repairable" and can_manage_campaign_session(campaign_slug):
            links["progression_repair_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/progression-repair",
            )
            links["flask_progression_repair_url"] = url_for(
                "character_progression_repair_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        return links

    def serialize_character_level_up_response(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        readiness: dict[str, Any] | None = None,
        level_up_context: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        readiness = readiness or character_level_up_readiness(campaign_slug, campaign, record)
        readiness_status = str(readiness.get("status") or "").strip() or "unsupported"
        supported = character_level_up_is_supported(readiness)
        lane = "dnd5e" if supported else ("repairable" if readiness_status == "repairable" else "unsupported")
        unsupported_message = "" if supported else str(readiness.get("message") or "This character is not ready for Gen2 level-up.")
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "character": serialize_character_record(campaign_slug, record),
                "lane": lane,
                "supported": supported,
                "message": message,
                "unsupported_message": unsupported_message,
                "readiness": make_json_safe(readiness),
                "level_up": (
                    serialize_character_level_up_context(level_up_context)
                    if level_up_context is not None
                    else None
                ),
                "links": character_level_up_links(campaign_slug, campaign, record, readiness),
            }
        )

    def load_character_level_up_target(campaign_slug: str, character_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if not has_session_mode_access(campaign_slug, character_slug):
            return campaign, None, json_error(
                "You do not have permission to level up this character.",
                403,
                code="forbidden",
            )
        record = load_character_record(campaign_slug, character_slug)
        return campaign, record, None

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/level-up")
    @api_login_required
    def character_level_up_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_level_up_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        readiness = character_level_up_readiness(campaign_slug, campaign, record)
        if not character_level_up_is_supported(readiness):
            return serialize_character_level_up_response(campaign_slug, campaign, record, readiness=readiness)
        form_values = normalize_character_level_up_values(dict(request.args))
        try:
            level_up_context = build_character_level_up_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
        except CharacterBuildError as exc:
            readiness = {"status": "unsupported", "message": str(exc)}
            return serialize_character_level_up_response(campaign_slug, campaign, record, readiness=readiness)
        return serialize_character_level_up_response(
            campaign_slug,
            campaign,
            record,
            readiness=readiness,
            level_up_context=level_up_context,
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/level-up")
    @api_login_required
    def character_level_up_submit(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_level_up_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        readiness = character_level_up_readiness(campaign_slug, campaign, record)
        if not character_level_up_is_supported(readiness):
            return json_error(
                str(readiness.get("message") or "This character is not ready for Gen2 level-up."),
                400,
                code="unsupported_campaign_system",
            )
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            form_values = normalize_character_level_up_values(payload)
            level_up_context = build_character_level_up_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            target_level = int(level_up_context.get("next_level") or 0)
            definition, import_metadata, hp_gain = build_native_level_up_character_definition(
                campaign_slug,
                record.definition,
                level_up_context,
                form_values,
                current_import_metadata=record.import_metadata,
            )
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                hp_delta=hp_gain,
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            return json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CharacterBuildError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refreshed_record = load_character_record(campaign_slug, character_slug)
        refreshed_readiness = character_level_up_readiness(campaign_slug, campaign, refreshed_record)
        refreshed_context = None
        if character_level_up_is_supported(refreshed_readiness):
            refreshed_context = build_character_level_up_context_parts(campaign_slug, campaign, refreshed_record)
        return serialize_character_level_up_response(
            campaign_slug,
            campaign,
            refreshed_record,
            readiness=refreshed_readiness,
            level_up_context=refreshed_context,
            message=f"{definition.name} advanced to level {target_level}.",
        )

    def normalize_character_progression_repair_values(payload: dict[str, Any]) -> dict[str, str]:
        raw_values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
        values: dict[str, str] = {}
        for key, value in dict(raw_values or {}).items():
            field_name = str(key or "").strip()
            if not field_name:
                continue
            if isinstance(value, list):
                values[field_name] = str(value[-1] if value else "")
            elif value is None:
                values[field_name] = ""
            else:
                values[field_name] = str(value)
        return values

    def character_progression_repair_readiness(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
    ) -> dict[str, Any]:
        campaign_system = getattr(campaign, "system", "")
        if character_advancement_lane(campaign_system) != CHARACTER_ADVANCEMENT_LANE_DND5E_LEVEL_UP:
            return {
                "status": "unsupported",
                "message": character_advancement_unsupported_message(campaign_system),
            }
        if not supports_native_character_tools(getattr(record.definition, "system", "")):
            return {
                "status": "unsupported",
                "message": "Progression repair is currently available only for DND-5E imported character sheets in Gen2.",
            }
        return native_level_up_readiness(
            current_app.extensions["systems_service"],
            campaign_slug,
            record.definition,
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )

    def character_progression_repair_is_supported(readiness: dict[str, Any]) -> bool:
        return str(readiness.get("status") or "").strip() == "repairable"

    def build_character_progression_repair_context_parts(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        form_values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        repair_context = build_imported_progression_repair_context(
            current_app.extensions["systems_service"],
            campaign_slug,
            record.definition,
            form_values=form_values,
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )
        repair_context["state_revision"] = record.state_record.revision
        return repair_context

    def serialize_character_progression_repair_context(repair_context: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "state_revision",
            "values",
            "character_name",
            "current_level",
            "readiness",
            "class_rows",
            "species_options",
            "background_options",
            "feat_rows",
            "optionalfeature_rows",
            "spell_rows",
        )
        return {key: make_json_safe(repair_context.get(key)) for key in keys}

    def character_progression_repair_links(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        readiness: dict[str, Any],
    ) -> dict[str, str]:
        character_slug = record.definition.character_slug
        links = {
            **serialize_character_links(campaign_slug, campaign, record),
            "character_url": gen2_campaign_href(campaign_slug, f"characters/{character_slug}"),
            "flask_character_url": url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            ),
        }
        readiness_status = str(readiness.get("status") or "").strip()
        if readiness_status == "repairable":
            links["progression_repair_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/progression-repair",
            )
            links["flask_progression_repair_url"] = url_for(
                "character_progression_repair_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        elif readiness_status == "ready":
            links["level_up_url"] = gen2_campaign_href(
                campaign_slug,
                f"characters/{character_slug}/level-up",
            )
            links["flask_level_up_url"] = url_for(
                "character_level_up_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        return links

    def serialize_character_progression_repair_response(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        readiness: dict[str, Any] | None = None,
        repair_context: dict[str, Any] | None = None,
        message: str | None = None,
    ):
        readiness = readiness or character_progression_repair_readiness(campaign_slug, campaign, record)
        readiness_status = str(readiness.get("status") or "").strip() or "unsupported"
        supported = character_progression_repair_is_supported(readiness)
        if supported:
            lane = "repairable"
            unsupported_message = ""
        elif readiness_status == "ready":
            lane = "ready"
            unsupported_message = "This character is already ready for native level-up."
        else:
            lane = "unsupported"
            unsupported_message = str(
                readiness.get("message") or "This character cannot use the current native progression flow."
            )
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "character": serialize_character_record(campaign_slug, record),
                "lane": lane,
                "supported": supported,
                "message": message,
                "unsupported_message": unsupported_message,
                "readiness": make_json_safe(readiness),
                "repair": (
                    serialize_character_progression_repair_context(repair_context)
                    if repair_context is not None and supported
                    else None
                ),
                "links": character_progression_repair_links(campaign_slug, campaign, record, readiness),
            }
        )

    def load_character_progression_repair_target(campaign_slug: str, character_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        record = load_character_record(campaign_slug, character_slug)
        if not can_manage_campaign_session(campaign_slug):
            return campaign, record, json_error(
                "You do not have permission to repair progression for this character.",
                403,
                code="forbidden",
            )
        return campaign, record, None

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_progression_repair_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_progression_repair_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        readiness = character_progression_repair_readiness(campaign_slug, campaign, record)
        if not character_progression_repair_is_supported(readiness):
            return serialize_character_progression_repair_response(campaign_slug, campaign, record, readiness=readiness)
        form_values = normalize_character_progression_repair_values(dict(request.args))
        try:
            repair_context = build_character_progression_repair_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values or None,
            )
        except CharacterBuildError as exc:
            readiness = {"status": "unsupported", "message": str(exc)}
            return serialize_character_progression_repair_response(campaign_slug, campaign, record, readiness=readiness)
        return serialize_character_progression_repair_response(
            campaign_slug,
            campaign,
            record,
            readiness=readiness,
            repair_context=repair_context,
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_progression_repair_submit(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_progression_repair_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        readiness = character_progression_repair_readiness(campaign_slug, campaign, record)
        if not character_progression_repair_is_supported(readiness):
            return json_error(
                str(readiness.get("message") or "This character is not ready for Gen2 progression repair."),
                400,
                code="unsupported_campaign_system",
            )
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            form_values = normalize_character_progression_repair_values(payload)
            repair_context = build_character_progression_repair_context_parts(
                campaign_slug,
                campaign,
                record,
                form_values=form_values,
            )
            definition, import_metadata = apply_imported_progression_repairs(
                campaign_slug,
                record.definition,
                record.import_metadata,
                repair_context,
                form_values,
            )
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
            )
            merged_state = merge_state_with_definition(definition, record.state_record.state)
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            return json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CharacterBuildError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refreshed_record = load_character_record(campaign_slug, character_slug)
        refreshed_readiness = character_progression_repair_readiness(campaign_slug, campaign, refreshed_record)
        refreshed_context = None
        if character_progression_repair_is_supported(refreshed_readiness):
            refreshed_context = build_character_progression_repair_context_parts(campaign_slug, campaign, refreshed_record)
            repair_message = (
                "Progression repair saved, but this character still needs a few more linked details before native level-up."
            )
        elif str(refreshed_readiness.get("status") or "").strip() == "ready":
            repair_message = f"{definition.name} is ready for native level-up."
        else:
            repair_message = str(
                refreshed_readiness.get("message") or "This character cannot use the current native progression flow."
            )
        return serialize_character_progression_repair_response(
            campaign_slug,
            campaign,
            refreshed_record,
            readiness=refreshed_readiness,
            repair_context=refreshed_context,
            message=repair_message,
        )

    def normalize_cultivation_values(payload: dict[str, Any]) -> dict[str, str]:
        raw_values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
        values: dict[str, str] = {}
        for key, value in dict(raw_values or {}).items():
            field_name = str(key or "").strip()
            if not field_name:
                continue
            values[field_name] = "" if value is None else str(value)
        return values

    def normalize_cultivation_int(value: object, *, field_label: str, default: int = 0) -> int:
        raw_value = str(value or "").strip()
        if not raw_value:
            return default
        try:
            normalized_value = int(raw_value)
        except ValueError as exc:
            raise ValueError(f"{field_label} must be a whole number.") from exc
        if normalized_value < 0:
            raise ValueError(f"{field_label} must be zero or greater.")
        return normalized_value

    def character_cultivation_is_supported(campaign, record: CharacterRecord) -> bool:
        return bool(
            character_advancement_lane(getattr(campaign, "system", ""))
            == CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
            and is_xianxia_system(getattr(record.definition, "system", ""))
        )

    def build_xianxia_cultivation_parts(campaign_slug: str, campaign, record: CharacterRecord) -> dict[str, Any]:
        character = present_character_detail(
            campaign,
            record,
            include_player_notes_section=True,
            systems_service=current_app.extensions["systems_service"],
            campaign_page_records=list_visible_character_page_records(campaign_slug, campaign),
        )
        xianxia_read = character.get("xianxia_read")
        if not isinstance(xianxia_read, dict):
            abort(404)
        generic_technique_options = []
        for option in list_xianxia_generic_technique_learning_options(
            record.definition,
            campaign_slug=campaign_slug,
            systems_service=current_app.extensions["systems_service"],
        ):
            systems_ref = dict(option.get("systems_ref") or {})
            generic_technique_options.append(
                {
                    **option,
                    "href": build_character_entry_href(
                        campaign_slug,
                        systems_ref=systems_ref,
                    ),
                }
            )
        return xianxia_cultivation.present_xianxia_cultivation_context(
            character,
            record.definition.xianxia,
            generic_technique_learning_options=generic_technique_options,
        )

    def serialize_character_cultivation_response(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        message: str | None = None,
        anchor: str | None = None,
    ):
        supported = character_cultivation_is_supported(campaign, record)
        character_slug = record.definition.character_slug
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "character": serialize_character_record(campaign_slug, record),
                "lane": "xianxia" if supported else "unsupported",
                "supported": supported,
                "message": message,
                "anchor": anchor,
                "unsupported_message": (
                    ""
                    if supported
                    else "Cultivation is only available for Xianxia character sheets."
                ),
                "cultivation": (
                    make_json_safe(build_xianxia_cultivation_parts(campaign_slug, campaign, record))
                    if supported
                    else None
                ),
                "links": {
                    **serialize_character_links(campaign_slug, campaign, record),
                    "character_url": gen2_campaign_href(campaign_slug, f"characters/{character_slug}"),
                    "flask_character_url": url_for(
                        "character_read_view",
                        campaign_slug=campaign_slug,
                        character_slug=character_slug,
                    ),
                    "cultivation_url": gen2_campaign_href(
                        campaign_slug,
                        f"characters/{character_slug}/cultivation",
                    ),
                    "flask_cultivation_url": url_for(
                        "character_xianxia_cultivation_view",
                        campaign_slug=campaign_slug,
                        character_slug=character_slug,
                    ),
                },
            }
        )

    def load_character_cultivation_target(campaign_slug: str, character_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        record = load_character_record(campaign_slug, character_slug)
        if not can_manage_campaign_session(campaign_slug):
            return campaign, record, json_error(
                "You do not have permission to manage cultivation for this character.",
                403,
                code="forbidden",
            )
        return campaign, record, None

    def apply_xianxia_cultivation_action(
        campaign_slug: str,
        record: CharacterRecord,
        payload: dict[str, Any],
    ) -> tuple[object, str, str]:
        values = normalize_cultivation_values(payload)
        action = str(payload.get("action") or values.get("cultivation_action") or "save_insight").strip()
        redirect_anchor = "xianxia-cultivation-insight"
        if action == "save_insight":
            definition = xianxia_cultivation.update_xianxia_insight_definition(
                record.definition,
                available=normalize_cultivation_int(
                    values.get("insight_available", ""),
                    field_label="Insight available",
                ),
                spent=normalize_cultivation_int(
                    values.get("insight_spent", ""),
                    field_label="Insight spent",
                ),
            )
            return definition, "Insight counters saved.", redirect_anchor
        if action == "record_gathering_insight":
            redirect_anchor = "xianxia-cultivation-gathering-insight"
            definition = xianxia_cultivation.update_xianxia_gathering_insight_definition(
                record.definition,
                amount=normalize_cultivation_int(
                    values.get("insight_gain_amount", ""),
                    field_label="Gathered Insight",
                ),
                downtime=values.get("gathering_insight_downtime", ""),
                notes=values.get("gathering_insight_notes", ""),
            )
            return definition, "Gathering Insight recorded.", redirect_anchor
        if action == "spend_cultivation_energy":
            redirect_anchor = "xianxia-cultivation-energy"
            energy_result = spend_xianxia_cultivation_energy_definition(
                record.definition,
                energy_key=values.get("energy_key", ""),
                notes=values.get("cultivation_energy_notes", ""),
            )
            return (
                energy_result.definition,
                f"Spent {energy_result.insight_cost} Insight on Cultivation to increase {energy_result.energy_name}.",
                redirect_anchor,
            )
        if action == "spend_meditation_yin_yang":
            redirect_anchor = "xianxia-cultivation-meditation"
            meditation_result = spend_xianxia_meditation_definition(
                record.definition,
                yin_yang_key=values.get("yin_yang_key", ""),
                notes=values.get("meditation_notes", ""),
            )
            return (
                meditation_result.definition,
                f"Spent {meditation_result.insight_cost} Insight on Meditation to increase {meditation_result.yin_yang_name}.",
                redirect_anchor,
            )
        if action == "spend_conditioning":
            redirect_anchor = "xianxia-cultivation-conditioning"
            conditioning_result = spend_xianxia_conditioning_definition(
                record.definition,
                conditioning_target=values.get("conditioning_target", ""),
                effort_key=values.get("effort_key", ""),
                notes=values.get("conditioning_notes", ""),
            )
            return (
                conditioning_result.definition,
                f"Spent {conditioning_result.insight_cost} Insight on Conditioning to increase {conditioning_result.target_name}.",
                redirect_anchor,
            )
        if action == "spend_training":
            redirect_anchor = "xianxia-cultivation-training"
            training_result = spend_xianxia_training_definition(
                record.definition,
                training_target=values.get("training_target", ""),
                attribute_key=values.get("attribute_key", ""),
                notes=values.get("training_notes", ""),
            )
            return (
                training_result.definition,
                f"Spent {training_result.insight_cost} Insight on Training to increase {training_result.target_name}.",
                redirect_anchor,
            )
        if action == "advance_martial_art_rank":
            redirect_anchor = "xianxia-cultivation-martial-arts"
            raw_martial_art_index = values.get("martial_art_index", "")
            if not str(raw_martial_art_index or "").strip():
                raise ValueError("Martial Art selection is required.")
            rank_result = advance_xianxia_martial_art_rank_definition(
                record.definition,
                campaign_slug=campaign_slug,
                systems_service=current_app.extensions["systems_service"],
                martial_art_index=normalize_cultivation_int(
                    raw_martial_art_index,
                    field_label="Martial Art selection",
                ),
                target_rank_key=values.get("target_rank_key", ""),
                legendary_quest_note=values.get("legendary_quest_note", ""),
            )
            return (
                rank_result.definition,
                f"Spent {rank_result.insight_cost} Insight to advance {rank_result.martial_art_name} to {rank_result.rank_name}.",
                redirect_anchor,
            )
        if action == "learn_generic_technique":
            redirect_anchor = "xianxia-cultivation-techniques"
            technique_result = learn_xianxia_generic_technique_definition(
                record.definition,
                campaign_slug=campaign_slug,
                systems_service=current_app.extensions["systems_service"],
                generic_technique_entry_key=values.get("generic_technique_entry_key", ""),
                notes=values.get("generic_technique_notes", ""),
            )
            return (
                technique_result.definition,
                f"Spent {technique_result.insight_cost} Insight to learn {technique_result.technique_name}.",
                redirect_anchor,
            )
        if action == "start_realm_ascension_review":
            redirect_anchor = "xianxia-cultivation-realm-ascension"
            realm_result = start_xianxia_realm_ascension_review_definition(
                record.definition,
                target_realm=values.get("target_realm", ""),
                gm_review_note=values.get("realm_ascension_gm_review_note", ""),
                seclusion_notes=values.get("realm_ascension_seclusion_notes", ""),
                hp_stance_trade_notes=values.get("realm_ascension_hp_stance_trade_notes", ""),
            )
            return (
                realm_result.definition,
                f"Started Realm ascension review from {realm_result.current_realm} to {realm_result.target_realm}.",
                redirect_anchor,
            )
        if action == "reset_realm_ascension_stats":
            redirect_anchor = "xianxia-cultivation-realm-ascension"
            reset_result = reset_xianxia_realm_ascension_stats_definition(
                record.definition,
                target_realm=values.get("target_realm", ""),
                notes=values.get("realm_ascension_reset_notes", ""),
            )
            return (
                reset_result.definition,
                f"Reset Attributes and Efforts for {reset_result.current_realm} to {reset_result.target_realm} Realm ascension.",
                redirect_anchor,
            )
        if action == "apply_immortal_realm_rebuild":
            redirect_anchor = "xianxia-cultivation-realm-ascension"
            rebuild_result = apply_xianxia_immortal_realm_rebuild_definition(
                record.definition,
                target_realm=values.get("target_realm", ""),
                attribute_scores={
                    key: values.get(f"realm_rebuild_attribute_{key}", "")
                    for key in XIANXIA_ATTRIBUTE_KEYS
                },
                effort_scores={
                    key: values.get(f"realm_rebuild_effort_{key}", "")
                    for key in XIANXIA_EFFORT_KEYS
                },
                hp_maximum_trade=values.get("realm_ascension_trade_hp", ""),
                stance_maximum_trade=values.get("realm_ascension_trade_stance", ""),
                notes=values.get("realm_ascension_rebuild_notes", ""),
            )
            return (
                rebuild_result.definition,
                f"Applied the Immortal rebuild budget for {rebuild_result.total_rebuild_points} points and {rebuild_result.actions_per_turn} actions.",
                redirect_anchor,
            )
        if action == "apply_divine_realm_rebuild":
            redirect_anchor = "xianxia-cultivation-realm-ascension"
            rebuild_result = apply_xianxia_divine_realm_rebuild_definition(
                record.definition,
                target_realm=values.get("target_realm", ""),
                attribute_scores={
                    key: values.get(f"realm_rebuild_attribute_{key}", "")
                    for key in XIANXIA_ATTRIBUTE_KEYS
                },
                effort_scores={
                    key: values.get(f"realm_rebuild_effort_{key}", "")
                    for key in XIANXIA_EFFORT_KEYS
                },
                hp_maximum_trade=values.get("realm_ascension_trade_hp", ""),
                stance_maximum_trade=values.get("realm_ascension_trade_stance", ""),
                notes=values.get("realm_ascension_rebuild_notes", ""),
            )
            return (
                rebuild_result.definition,
                f"Applied the Divine rebuild budget for {rebuild_result.total_rebuild_points} points and {rebuild_result.actions_per_turn} actions.",
                redirect_anchor,
            )
        if action == "confirm_realm_ascension":
            redirect_anchor = "xianxia-cultivation-realm-ascension"
            confirmation_result = confirm_xianxia_realm_ascension_definition(
                record.definition,
                target_realm=values.get("target_realm", ""),
                gm_confirmation_note=values.get("realm_ascension_gm_confirmation_note", ""),
            )
            return (
                confirmation_result.definition,
                f"Recorded GM confirmation for the {confirmation_result.target_realm} Realm ascension.",
                redirect_anchor,
            )
        raise ValueError("Unsupported cultivation action. Refresh the page and try again.")

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/cultivation")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_cultivation_read(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_cultivation_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        return serialize_character_cultivation_response(campaign_slug, campaign, record)

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/cultivation")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_cultivation_action(campaign_slug: str, character_slug: str):
        campaign, record, access_error = load_character_cultivation_target(campaign_slug, character_slug)
        if access_error is not None:
            return access_error
        if not character_cultivation_is_supported(campaign, record):
            return json_error(
                "Cultivation is only available for Xianxia character sheets.",
                400,
                code="unsupported_campaign_system",
            )
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")
        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            definition, success_message, anchor = apply_xianxia_cultivation_action(
                campaign_slug,
                record,
                payload,
            )
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            return json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refreshed_record = load_character_record(campaign_slug, character_slug)
        return serialize_character_cultivation_response(
            campaign_slug,
            campaign,
            refreshed_record,
            message=success_message,
            anchor=anchor,
        )

    def serialize_character_controls(campaign_slug: str, campaign, record: CharacterRecord) -> dict[str, Any] | None:
        character_slug = record.definition.character_slug
        if not supports_character_controls_routes(getattr(campaign, "system", "")):
            return None
        if not has_session_mode_access(campaign_slug, character_slug):
            return None

        store = get_auth_store()
        user = get_current_user()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        assigned_user = store.get_user_by_id(assignment.user_id) if assignment is not None else None
        can_assign_owner = bool(user and user.is_admin)

        player_choices = (
            build_active_player_choices(
                store,
                campaign_slug,
                current_user_id=assignment.user_id if assignment is not None else None,
                include_current=True,
            )
            if can_assign_owner
            else []
        )

        return {
            "available": True,
            "assignment": (
                {
                    "user_id": assignment.user_id,
                    "assignment_type": assignment.assignment_type,
                    "display_name": assigned_user.display_name if assigned_user is not None else "Unknown user",
                    "email": assigned_user.email if assigned_user is not None else None,
                    "admin_href": (
                        url_for("admin_user_detail", user_id=assigned_user.id)
                        if can_assign_owner and assigned_user is not None
                        else None
                    ),
                }
                if assignment is not None
                else None
            ),
            "can_assign_owner": can_assign_owner,
            "can_delete_character": can_manage_campaign_content(campaign_slug),
            "current_user_is_owner": bool(user and assignment and assignment.user_id == user.id),
            "player_choices": player_choices,
            "links": {
                "flask_controls_url": url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                    page="controls",
                ),
                "gen2_roster_url": gen2_campaign_href(campaign_slug, "characters"),
            },
        }

    def serialize_character_summary(campaign, record: CharacterRecord) -> dict[str, Any]:
        presented = present_character_roster([record])[0]
        return {
            **presented,
            "system": record.definition.system,
            "href": gen2_campaign_href(campaign.slug, f"characters/{record.definition.character_slug}"),
            "flask_href": url_for(
                "character_read_view",
                campaign_slug=campaign.slug,
                character_slug=record.definition.character_slug,
            ),
            "portrait": build_character_portrait_payload(campaign, record),
            "revision": record.state_record.revision,
        }

    def build_character_item_catalog(campaign_slug: str) -> dict[str, object]:
        systems_service = current_app.extensions["systems_service"]
        item_catalog = _build_item_catalog(
            _list_campaign_enabled_entries(
                systems_service,
                campaign_slug,
                "item",
            )
        )
        campaign_item_pages = [
            page_record
            for page_record in get_campaign_page_store().list_page_records(campaign_slug, include_body=True)
            if str(getattr(getattr(page_record, "page", None), "section", "") or "").strip() == CAMPAIGN_ITEMS_SECTION
        ]
        return _attach_campaign_item_page_support(item_catalog, campaign_item_pages)

    def list_visible_character_page_records(campaign_slug: str, campaign) -> list[object]:
        return list_visible_character_page_records_for_store(
            get_campaign_page_store(),
            campaign_slug,
            campaign,
            include_body=True,
        )

    def build_record_equipment_support_lookup(
        record: CharacterRecord,
        *,
        item_catalog: dict[str, object],
    ) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
        normalized_definition_equipment = _normalize_equipment_payloads(
            list(record.definition.equipment_catalog or []),
            item_catalog=item_catalog,
        )
        definition_item_lookup = {
            str(item.get("id") or "").strip(): dict(item)
            for item in normalized_definition_equipment
            if str(item.get("id") or "").strip()
        }
        support_lookup: dict[str, dict[str, object]] = {}
        for inventory_item in list((record.state_record.state or {}).get("inventory") or []):
            item_ref = build_character_inventory_item_ref(inventory_item)
            if not item_ref:
                continue
            definition_item = dict(definition_item_lookup.get(item_ref) or {})
            support_item = dict(definition_item or inventory_item or {})
            if not str(support_item.get("name") or "").strip():
                support_item["name"] = str(dict(inventory_item or {}).get("name") or "").strip()
            support_lookup[item_ref] = describe_equipment_state_support(
                support_item,
                item_catalog=item_catalog,
            )
        return definition_item_lookup, support_lookup

    def build_character_equipment_state_payload(
        campaign_slug: str,
        record: CharacterRecord,
        *,
        campaign=None,
        campaign_page_records: list[object] | None = None,
    ) -> dict[str, Any]:
        resolved_campaign = campaign or get_repository().get_campaign(campaign_slug)
        resolved_campaign_page_records = (
            campaign_page_records
            if campaign_page_records is not None
            else list_visible_character_page_records(campaign_slug, resolved_campaign)
            if resolved_campaign is not None
            else []
        )
        systems_service = current_app.extensions["systems_service"]
        item_catalog = build_character_item_catalog(campaign_slug)
        definition_item_lookup, support_lookup = build_record_equipment_support_lookup(
            record,
            item_catalog=item_catalog,
        )
        equipment_items: list[dict[str, Any]] = []
        state = dict(record.state_record.state or {})
        inventory_lookup = {
            build_character_inventory_item_ref(item): dict(item)
            for item in list(state.get("inventory") or [])
            if build_character_inventory_item_ref(item)
        }
        for item_ref, inventory_item in inventory_lookup.items():
            definition_item = dict(definition_item_lookup.get(item_ref) or {})
            support = dict(support_lookup.get(item_ref) or {})
            if not bool(support.get("supports_equipped_state")):
                continue
            support_item = {
                **definition_item,
                **inventory_item,
            }
            requires_attunement = bool(support.get("requires_attunement"))
            supports_weapon_wield_mode = bool(support.get("supports_weapon_wield_mode"))
            resolved_weapon_wield_mode = resolve_weapon_wield_mode(
                support_item,
                item_catalog=item_catalog,
                support=support,
            )
            is_equipped = (
                bool(resolved_weapon_wield_mode)
                if supports_weapon_wield_mode
                else bool(inventory_item.get("is_equipped", False))
            )
            equipped_label = (
                weapon_wield_mode_label(resolved_weapon_wield_mode)
                if supports_weapon_wield_mode and is_equipped
                else "Equipped"
                if is_equipped
                else "Not equipped"
            )
            href = build_character_entry_href(
                campaign_slug,
                systems_ref=definition_item.get("systems_ref"),
                page_ref=definition_item.get("page_ref"),
            )
            description_html = (
                resolve_item_description_html(
                    resolved_campaign,
                    definition_item,
                    systems_service=systems_service,
                    campaign_page_records=resolved_campaign_page_records,
                )
                if resolved_campaign is not None and href
                else ""
            )
            equipment_items.append(
                {
                    "id": item_ref,
                    "name": str(inventory_item.get("name") or definition_item.get("name") or "Item").strip(),
                    "quantity": int(inventory_item.get("quantity") or definition_item.get("default_quantity") or 0),
                    "weight": str(inventory_item.get("weight") or definition_item.get("weight") or "").strip(),
                    "notes": str(inventory_item.get("notes") or definition_item.get("notes") or "").strip(),
                    "tags": [
                        str(tag).strip()
                        for tag in list(inventory_item.get("tags") or definition_item.get("tags") or [])
                        if str(tag).strip()
                    ],
                    "href": href,
                    "description_html": description_html,
                    "is_equipped": is_equipped,
                    "equipped_label": equipped_label,
                    "is_attuned": bool(inventory_item.get("is_attuned", False)) if requires_attunement else False,
                    "requires_attunement": requires_attunement,
                    "supports_attunement": requires_attunement,
                    "supports_weapon_wield_mode": supports_weapon_wield_mode,
                    "weapon_wield_mode": resolved_weapon_wield_mode,
                    "weapon_wield_options": [
                        {
                            "value": value,
                            "label": weapon_wield_mode_label(value),
                        }
                        for value in list(support.get("weapon_wield_modes") or [])
                        if weapon_wield_mode_label(value)
                    ],
                    "attunement_hint": "Requires attunement" if requires_attunement else "",
                    "source_label": (
                        f"Systems item ({dict(definition_item.get('systems_ref') or {}).get('source_id') or 'Unknown source'})"
                        if dict(definition_item.get("systems_ref") or {})
                        else "Campaign item"
                        if str(definition_item.get("page_ref") or "").strip()
                        else "Custom item"
                        if str(definition_item.get("source_kind") or "").strip() == "manual_edit"
                        else "Sheet item"
                    ),
                }
            )

        max_attuned_items = int((state.get("attunement") or {}).get("max_attuned_items") or 3)
        attuned_count = sum(1 for item in equipment_items if bool(item.get("is_attuned")))
        equipped_count = sum(1 for item in equipment_items if bool(item.get("is_equipped")))
        arcane_armor_state = present_arcane_armor_state(
            record.definition,
            state,
            inventory_lookup=inventory_lookup,
            equipment_catalog_lookup=definition_item_lookup,
        )
        return {
            "rows": equipment_items,
            "attuned_count": attuned_count,
            "equipped_count": equipped_count,
            "max_attuned_items": max_attuned_items,
            "equipment_item_refs": [
                str(item.get("id") or "").strip()
                for item in equipment_items
                if str(item.get("id") or "").strip()
            ],
            "attunable_item_refs": [
                str(item.get("id") or "").strip()
                for item in equipment_items
                if bool(item.get("requires_attunement")) and str(item.get("id") or "").strip()
            ],
            "at_attunement_limit": attuned_count >= max_attuned_items if max_attuned_items > 0 else True,
            "over_attunement_limit": attuned_count > max_attuned_items,
            "arcane_armor_state": arcane_armor_state,
        }

    def serialize_character_record(campaign_slug: str, record: CharacterRecord) -> dict[str, Any]:
        campaign = get_repository().get_campaign(campaign_slug)
        campaign_page_records = (
            list_visible_character_page_records(campaign_slug, campaign) if campaign is not None else []
        )
        presented_character = (
            present_character_detail(
                campaign,
                record,
                systems_service=current_app.extensions["systems_service"],
                campaign_page_records=campaign_page_records,
            )
            if campaign is not None
            else {}
        )
        equipment_state = build_character_equipment_state_payload(
            campaign_slug,
            record,
            campaign=campaign,
            campaign_page_records=campaign_page_records,
        )
        return {
            "definition": record.definition.to_dict(),
            "import_metadata": record.import_metadata.to_dict(),
            "state_record": serialize_character_state(record.state_record),
            "equipment_state": equipment_state,
            "arcane_armor_state": equipment_state.get("arcane_armor_state"),
            "presented_spellcasting": dict(presented_character.get("spellcasting") or {}),
            "presented_inventory": list(presented_character.get("inventory") or []),
            "presented_xianxia": dict(presented_character.get("xianxia_read") or {}),
            "overview_stats": [dict(stat) for stat in list(presented_character.get("overview_stats") or []) if isinstance(stat, dict)],
            "overview_stat_rows": [
                [dict(stat) for stat in list(row) if isinstance(stat, dict)]
                for row in list(presented_character.get("overview_stat_rows") or [])
                if isinstance(row, list)
            ],
            "player_notes_markdown": str(presented_character.get("player_notes_markdown") or ""),
            "player_notes_html": str(presented_character.get("player_notes_html") or ""),
            "reference_sections": [
                dict(section) for section in list(presented_character.get("reference_sections") or []) if isinstance(section, dict)
            ],
            "physical_description_markdown": str(presented_character.get("physical_description_markdown") or ""),
            "physical_description_html": str(presented_character.get("physical_description_html") or ""),
            "personal_background_markdown": str(presented_character.get("personal_background_markdown") or ""),
            "personal_background_html": str(presented_character.get("personal_background_html") or ""),
            "abilities": [dict(ability) for ability in list(presented_character.get("abilities") or []) if isinstance(ability, dict)],
            "skills": [dict(skill) for skill in list(presented_character.get("skills") or []) if isinstance(skill, dict)],
            "proficiency_groups": [
                dict(group) for group in list(presented_character.get("proficiency_groups") or []) if isinstance(group, dict)
            ],
            "portrait": build_character_portrait_payload(campaign, record) if campaign is not None else None,
            "controls": serialize_character_controls(campaign_slug, campaign, record) if campaign is not None else None,
            "permissions": {
                "can_edit_session": has_session_mode_access(campaign_slug, record.definition.character_slug),
                "can_manage_session": can_manage_campaign_session(campaign_slug),
                "can_use_controls": (
                    campaign is not None
                    and supports_character_controls_routes(getattr(campaign, "system", ""))
                    and has_session_mode_access(campaign_slug, record.definition.character_slug)
                ),
                "can_record_xianxia_dao_immolating_use": can_manage_campaign_session(campaign_slug),
            },
        }

    def serialize_character_file_record(record) -> dict[str, Any]:
        return {
            "character_slug": record.character_slug,
            "updated_at": record.updated_at,
            "definition": record.definition.to_dict(),
            "import_metadata": record.import_metadata.to_dict(),
            "state_created": record.state_created,
        }

    def serialize_character_file_summary(record) -> dict[str, Any]:
        return {
            "character_slug": record.character_slug,
            "updated_at": record.updated_at,
            "name": record.definition.name,
            "status": record.definition.status,
            "import_status": record.import_metadata.import_status,
        }

    def get_character_repository():
        return current_app.extensions["character_repository"]

    def get_character_state_service():
        return current_app.extensions["character_state_service"]

    def load_character_record(campaign_slug: str, character_slug: str) -> CharacterRecord:
        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        if record is None:
            abort(404)
        return record

    def serialize_updated_character(campaign_slug: str, character_slug: str):
        updated_record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        if updated_record is None:
            abort(404)
        return jsonify(
            {
                "ok": True,
                "character": serialize_character_record(campaign_slug, updated_record),
            }
        )

    def serialize_theme_preset(preset) -> dict[str, Any]:
        return {
            "key": preset.key,
            "label": preset.label,
            "description": preset.description,
            "preview_colors": list(preset.preview_colors),
        }

    @api.get("/me")
    @api_login_required
    def me():
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")
        return jsonify(
            {
                "ok": True,
                "app": serialize_app_state(),
                "auth_source": get_current_auth_source(),
                "user": serialize_user(user),
                "memberships": [serialize_membership(item) for item in get_current_memberships()],
                "preferences": {
                    "theme_key": get_current_user_preferences().theme_key,
                    "session_chat_order": get_current_user_preferences().session_chat_order,
                    "frontend_mode": get_current_user_preferences().frontend_mode,
                },
            }
        )

    @api.get("/me/settings")
    @api_login_required
    def me_settings():
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        preferences = get_current_user_preferences()
        return jsonify(
            {
                "ok": True,
                "theme_presets": [serialize_theme_preset(preset) for preset in list_theme_presets()],
                "session_chat_order_choices": SESSION_CHAT_ORDER_CHOICES,
                "preferences": {
                    "theme_key": preferences.theme_key,
                    "session_chat_order": preferences.session_chat_order,
                    "frontend_mode": preferences.frontend_mode,
                },
                "user": serialize_user(user),
            }
        )

    @api.patch("/me/settings")
    @api_login_required
    def me_settings_update():
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        requested_theme_key = payload.get("theme_key", "")
        requested_chat_order = payload.get("session_chat_order", "")
        has_theme_update = bool(str(requested_theme_key).strip())
        has_chat_order_update = bool(str(requested_chat_order).strip())

        if "frontend_mode" in payload:
            return json_error(
                "Preferred frontend selection is no longer available.",
                400,
                code="validation_error",
            )

        if not has_theme_update and not has_chat_order_update:
            return json_error("No account settings were provided.", 400, code="validation_error")

        if has_theme_update:
            if not is_valid_theme_key(str(requested_theme_key)):
                return json_error("Choose a valid theme preset.", 400, code="validation_error")

        if has_chat_order_update:
            if not is_valid_session_chat_order(requested_chat_order):
                return json_error("Choose a valid live session chat order.", 400, code="validation_error")

        store = get_auth_store()
        current_preferences = store.get_user_preferences(user.id)
        normalized_theme_key = current_preferences.theme_key
        normalized_chat_order = current_preferences.session_chat_order

        if has_theme_update:
            normalized_theme_key = get_theme_preset(requested_theme_key).key
            if normalized_theme_key != current_preferences.theme_key:
                store.set_user_theme_key(user.id, normalized_theme_key)

        if has_chat_order_update:
            normalized_chat_order = normalize_session_chat_order(requested_chat_order)
            if normalized_chat_order != current_preferences.session_chat_order:
                store.set_user_session_chat_order(user.id, normalized_chat_order)

        updated_preferences = store.get_user_preferences(user.id)

        return jsonify(
            {
                "ok": True,
                "user": serialize_user(user),
                "preferences": {
                    "theme_key": updated_preferences.theme_key,
                    "session_chat_order": updated_preferences.session_chat_order,
                    "frontend_mode": updated_preferences.frontend_mode,
                },
            }
        )

    @api.get("/admin")
    @api_login_required
    @api_admin_required
    def admin_dashboard_api():
        return jsonify(build_admin_dashboard_context())

    @api.get("/admin/users/<int:user_id>")
    @api_login_required
    @api_admin_required
    def admin_user_detail_api(user_id: int):
        user = require_admin_target_user(user_id)
        return jsonify(build_admin_user_detail_context(user))

    @api.post("/admin/users/invite")
    @api_login_required
    @api_admin_required
    def admin_invite_user_api():
        store = get_auth_store()
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        email = str(payload.get("email") or "").strip()
        display_name = str(payload.get("display_name") or "").strip()
        requested_user_type = str(payload.get("user_type") or "").strip().lower()
        campaign_slug = str(payload.get("campaign_slug") or "").strip()

        if not requested_user_type:
            legacy_is_admin = str(payload.get("is_admin") or "").strip()
            if legacy_is_admin == "1":
                requested_user_type = "admin"
            elif legacy_is_admin == "0":
                requested_user_type = "standard"

        if requested_user_type not in {"admin", "dm", "player", "standard"}:
            return json_error("Choose a valid user type.", 400, code="validation_error")
        if requested_user_type in {"dm", "player"} and (
            not campaign_slug or get_repository().get_campaign(campaign_slug) is None
        ):
            return json_error("Choose a valid campaign for DM or Player invites.", 400, code="validation_error")

        make_admin = requested_user_type == "admin"

        if not email or not display_name:
            return json_error("Email and display name are required.", 400, code="validation_error")
        if store.get_user_by_email(email) is not None:
            return json_error(f"User already exists: {email}", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        user = store.create_user(
            email,
            display_name,
            is_admin=make_admin,
            status="invited",
        )
        invite_token = store.issue_invite_token(
            user.id,
            expires_in=timedelta(hours=current_app.config["INVITE_TTL_HOURS"]),
            created_by_user_id=actor_user_id,
        )
        store.write_audit_event(
            event_type="user_created",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"is_admin": make_admin, "source": "admin_screen"},
        )
        store.write_audit_event(
            event_type="user_invited",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        if requested_user_type in {"dm", "player"}:
            membership = store.upsert_membership(
                user.id,
                campaign_slug,
                role=requested_user_type,
                status="active",
            )
            store.write_audit_event(
                event_type="membership_created",
                actor_user_id=actor_user_id,
                target_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "role": membership.role,
                    "status": membership.status,
                    "source": "admin_screen",
                },
            )
        invite_url = build_admin_local_url(f"/invite/{invite_token}")
        detail_context = build_admin_user_detail_context(user)
        detail_context.update(
            {
                "message": f"Invite URL: {invite_url}",
                "invite_url": invite_url,
            }
        )
        return jsonify(detail_context), 201

    @api.post("/admin/users/<int:user_id>/membership")
    @api_login_required
    @api_admin_required
    def admin_set_membership_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        store = get_auth_store()
        campaign_slug = str(payload.get("campaign_slug") or "").strip()
        role = str(payload.get("role") or "").strip()
        status = str(payload.get("status") or "").strip()

        if not campaign_slug or get_repository().get_campaign(campaign_slug) is None:
            return json_error("Choose a valid campaign.", 400, code="validation_error")
        if role not in {"dm", "player", "observer"}:
            return json_error("Choose a valid campaign role.", 400, code="validation_error")
        if status not in {"active", "invited", "removed"}:
            return json_error("Choose a valid membership status.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        previous = store.get_membership(user.id, campaign_slug, statuses=None)
        membership = store.upsert_membership(user.id, campaign_slug, role=role, status=status)
        if previous is None or previous.status == "removed":
            event_type = "membership_created"
        elif membership.status == "removed":
            event_type = "membership_removed"
        else:
            event_type = "membership_role_changed"
        store.write_audit_event(
            event_type=event_type,
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={"role": membership.role, "status": membership.status, "source": "admin_screen"},
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Membership updated: {campaign_slug} -> {membership.role} ({membership.status})"
        return jsonify(context)

    @api.delete("/admin/users/<int:user_id>/membership")
    @api_login_required
    @api_admin_required
    def admin_remove_membership_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        store = get_auth_store()
        campaign_slug = str(payload.get("campaign_slug") or "").strip()
        membership = store.get_membership(user.id, campaign_slug, statuses=None)
        if membership is None:
            return json_error("Choose a valid membership to remove.", 400, code="validation_error")
        if membership.status == "removed":
            return json_error("That membership is already removed.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        updated_membership = store.upsert_membership(
            user.id,
            membership.campaign_slug,
            role=membership.role,
            status="removed",
        )
        store.write_audit_event(
            event_type="membership_removed",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=membership.campaign_slug,
            metadata={
                "role": updated_membership.role,
                "status": updated_membership.status,
                "source": "admin_screen",
            },
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Removed membership for {membership.campaign_slug}."
        return jsonify(context)

    @api.post("/admin/users/<int:user_id>/assignment")
    @api_login_required
    @api_admin_required
    def admin_assign_character_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        raw_assignment = str(payload.get("character_ref") or "").strip()
        if not raw_assignment:
            campaign_slug = str(payload.get("campaign_slug") or "").strip()
            character_slug = str(payload.get("character_slug") or "").strip()
            if campaign_slug and character_slug:
                raw_assignment = f"{campaign_slug}::{character_slug}"

        if "::" not in raw_assignment:
            return json_error("Choose a valid character.", 400, code="validation_error")

        campaign_slug, character_slug = raw_assignment.split("::", 1)
        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        if record is None:
            return json_error("Choose a valid visible character.", 400, code="validation_error")

        store = get_auth_store()
        membership = store.get_membership(user.id, campaign_slug, statuses=("active",))
        if membership is None or membership.role != "player":
            return json_error(
                "Character owners must have an active player membership in that campaign.",
                400,
                code="validation_error",
            )

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        previous = store.get_character_assignment(campaign_slug, character_slug)
        assignment = store.upsert_character_assignment(user.id, campaign_slug, character_slug)
        store.write_audit_event(
            event_type="character_assignment_created",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "previous_user_id": previous.user_id if previous is not None else None,
                "assignment_type": assignment.assignment_type,
                "source": "admin_screen",
            },
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Assigned {character_slug} in {campaign_slug} to {user.email}."
        return jsonify(context)

    @api.delete("/admin/users/<int:user_id>/assignment")
    @api_login_required
    @api_admin_required
    def admin_remove_character_assignment_api(user_id: int):
        user = require_admin_target_user(user_id)
        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        campaign_slug = str(payload.get("campaign_slug") or "").strip()
        character_slug = str(payload.get("character_slug") or "").strip()
        store = get_auth_store()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        if assignment is None or assignment.user_id != user.id:
            return json_error("Choose a valid character assignment to remove.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        removed_assignment = store.delete_character_assignment(campaign_slug, character_slug)
        if removed_assignment is None:
            return json_error("That character assignment no longer exists.", 400, code="validation_error")

        store.write_audit_event(
            event_type="character_assignment_removed",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "assignment_type": removed_assignment.assignment_type,
                "source": "admin_screen",
            },
        )
        context = build_admin_user_detail_context(user)
        context["message"] = f"Cleared assignment for {character_slug} in {campaign_slug}."
        return jsonify(context)

    @api.post("/admin/users/<int:user_id>/invite")
    @api_login_required
    @api_admin_required
    def admin_issue_invite_api(user_id: int):
        user = require_admin_target_user(user_id)
        if user.status != "invited":
            return json_error("Invite links are only available for invited users.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        store = get_auth_store()
        invite_token = store.issue_invite_token(
            user.id,
            expires_in=timedelta(hours=current_app.config["INVITE_TTL_HOURS"]),
            created_by_user_id=actor_user_id,
        )
        store.write_audit_event(
            event_type="user_invited",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        invite_url = build_admin_local_url(f"/invite/{invite_token}")
        context = build_admin_user_detail_context(user)
        context.update({"message": f"Invite URL: {invite_url}", "invite_url": invite_url})
        return jsonify(context)

    @api.post("/admin/users/<int:user_id>/password-reset")
    @api_login_required
    @api_admin_required
    def admin_issue_password_reset_api(user_id: int):
        user = require_admin_target_user(user_id)
        if not user.is_active:
            return json_error("Password resets are only available for active users.", 400, code="validation_error")

        actor = get_current_user()
        actor_user_id = actor.id if actor is not None else None
        store = get_auth_store()
        reset_token = store.issue_password_reset_token(
            user.id,
            expires_in=timedelta(hours=current_app.config["RESET_TTL_HOURS"]),
            created_by_user_id=actor_user_id,
        )
        store.write_audit_event(
            event_type="password_reset_issued",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        reset_url = build_admin_local_url(f"/reset/{reset_token}")
        context = build_admin_user_detail_context(user)
        context.update({"message": f"Password reset URL: {reset_url}", "reset_url": reset_url})
        return jsonify(context)

    @api.post("/admin/users/<int:user_id>/disable")
    @api_login_required
    @api_admin_required
    def admin_disable_user_api(user_id: int):
        user = require_admin_target_user(user_id)
        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            return json_error(
                "The admin screen will not disable the account you are currently using.",
                400,
                code="validation_error",
            )

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        updated_user = store.disable_user(user.id)
        store.revoke_all_user_sessions(user.id)
        store.revoke_all_user_api_tokens(user.id)
        store.write_audit_event(
            event_type="user_disabled",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"source": "admin_screen"},
        )
        context = build_admin_user_detail_context(updated_user)
        context["message"] = f"Disabled user {updated_user.email}."
        return jsonify(context)

    @api.post("/admin/users/<int:user_id>/enable")
    @api_login_required
    @api_admin_required
    def admin_enable_user_api(user_id: int):
        user = require_admin_target_user(user_id)
        if user.status != "disabled":
            return json_error("Only disabled users can be re-enabled.", 400, code="validation_error")

        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            return json_error(
                "The admin screen will not re-enable the account you are currently using.",
                400,
                code="validation_error",
            )

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        enabled_user = store.enable_user(user.id)
        store.write_audit_event(
            event_type="user_enabled",
            actor_user_id=actor_user_id,
            target_user_id=user.id,
            metadata={"status": enabled_user.status, "source": "admin_screen"},
        )
        context = build_admin_user_detail_context(enabled_user)
        if enabled_user.status == "active":
            context["message"] = f"Re-enabled user {enabled_user.email}."
        else:
            context["message"] = (
                f"Re-enabled user {enabled_user.email}. The account is back in invited status."
            )
        return jsonify(context)

    @api.delete("/admin/users/<int:user_id>")
    @api_login_required
    @api_admin_required
    def admin_delete_user_api(user_id: int):
        user = require_admin_target_user(user_id)
        actor = get_current_user()
        if actor is not None and actor.id == user.id:
            return json_error(
                "The admin screen will not delete the account you are currently using.",
                400,
                code="validation_error",
            )

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")
        confirm_email = str(payload.get("confirm_email") or payload.get("confirm_user_email") or "").strip()
        if confirm_email.lower() != user.email.lower():
            return json_error("Type the user's email address to confirm deletion.", 400, code="validation_error")

        store = get_auth_store()
        actor_user_id = actor.id if actor is not None else None
        deleted_user = store.delete_user(user.id)
        if deleted_user is None:
            abort(404)

        store.write_audit_event(
            event_type="user_deleted",
            actor_user_id=actor_user_id,
            metadata={
                "email": deleted_user.email,
                "status": deleted_user.status,
                "is_admin": deleted_user.is_admin,
                "source": "admin_screen",
            },
        )
        context = build_admin_dashboard_context()
        context.update(
            {
                "message": f"Deleted user {deleted_user.email}.",
                "deleted_user": serialize_user(deleted_user),
            }
        )
        return jsonify(context)

    @api.get("/app")
    def app_state():
        return jsonify({"ok": True, "app": serialize_app_state()})

    @api.get("/systems/import-runs")
    @api_login_required
    @api_admin_required
    def systems_import_run_list():
        raw_limit = request.args.get("limit", "20").strip()
        try:
            limit = int(raw_limit)
        except ValueError:
            return json_error("limit must be an integer.", 400, code="validation_error")

        library_slug = request.args.get("library_slug", "").strip() or None
        source_id = request.args.get("source_id", "").strip().upper() or None
        import_runs = current_app.extensions["systems_store"].list_import_runs(
            library_slug=library_slug,
            source_id=source_id,
            limit=limit,
        )
        return jsonify(
            {
                "ok": True,
                "import_runs": [serialize_systems_import_run(import_run) for import_run in import_runs],
            }
        )

    @api.get("/systems/import-runs/<int:import_run_id>")
    @api_login_required
    @api_admin_required
    def systems_import_run_detail(import_run_id: int):
        import_run = current_app.extensions["systems_store"].get_import_run(import_run_id)
        if import_run is None:
            abort(404)
        return jsonify({"ok": True, "import_run": serialize_systems_import_run(import_run)})

    @api.post("/systems/imports/dnd5e")
    @api_login_required
    @api_admin_required
    def systems_import_dnd5e():
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            source_ids = normalize_source_ids(payload.get("source_ids"))
            entry_types = payload.get("entry_types")
            if entry_types is not None:
                if not isinstance(entry_types, list):
                    raise ValueError("entry_types must be an array when provided.")
                entry_types = [str(item or "").strip().lower() for item in entry_types if str(item or "").strip()]
                invalid_entry_types = sorted(set(entry_types) - set(SUPPORTED_ENTRY_TYPES))
                if invalid_entry_types:
                    raise ValueError(
                        "Unsupported entry_types: " + ", ".join(invalid_entry_types)
                    )
            archive = decode_embedded_file(
                payload.get("archive"),
                label="archive",
            )
            archive_filename = str(archive["filename"] or "").strip()
            if not archive_filename.lower().endswith(".zip"):
                raise ValueError("archive filename must end with .zip.")
            import_version = str(payload.get("import_version") or "").strip() or Path(archive_filename).stem
            source_path_label = (
                str(payload.get("source_path_label") or "").strip()
                or f"api-upload:{archive_filename}"
            )
        except (SystemsIngestError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        try:
            with extracted_systems_archive(archive["data_blob"]) as data_root:
                importer = Dnd5eSystemsImporter(
                    store=current_app.extensions["systems_store"],
                    systems_service=current_app.extensions["systems_service"],
                    data_root=data_root,
                )
                results = importer.import_sources(
                    source_ids,
                    entry_types=entry_types,
                    started_by_user_id=user.id,
                    import_version=import_version,
                    source_path_label=source_path_label,
                )
        except (FileNotFoundError, SystemsIngestError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        import_runs = [
            current_app.extensions["systems_store"].get_import_run(result.import_run_id)
            for result in results
        ]
        return jsonify(
            {
                "ok": True,
                "import_results": [serialize_systems_import_result(result) for result in results],
                "import_runs": [
                    serialize_systems_import_run(import_run)
                    for import_run in import_runs
                    if import_run is not None
                ],
            }
        )

    @api.get("/campaigns")
    def campaigns():
        entries = get_accessible_campaign_entries() if get_current_user() is not None else get_public_campaign_entries()
        return jsonify(
            {
                "ok": True,
                "campaigns": [serialize_campaign_entry(entry) for entry in entries],
            }
        )

    @api.get("/campaigns/<campaign_slug>")
    @api_campaign_scope_access_required("campaign")
    def campaign_detail(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "role": get_campaign_role(campaign_slug),
                "auth_source": get_current_auth_source(),
                "visibility": serialize_visibility_map(campaign_slug),
                "permissions": {
                    "can_manage_content": can_manage_campaign_content(campaign_slug),
                    "can_manage_systems": can_manage_campaign_systems(campaign_slug),
                    "can_manage_combat": can_manage_campaign_combat(campaign_slug),
                    "can_manage_session": can_manage_campaign_session(campaign_slug),
                    "can_manage_dm_content": can_manage_campaign_dm_content(campaign_slug),
                    "can_manage_visibility": can_manage_campaign_visibility(campaign_slug),
                    "can_post_session_messages": can_post_campaign_session_messages(campaign_slug),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/control")
    @api_campaign_visibility_management_required
    def campaign_control(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        user = get_current_user()
        include_private = bool(user and user.is_admin)
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "visibility_rows": [
                    serialize_campaign_control_visibility_row(campaign_slug, scope)
                    for scope in CAMPAIGN_VISIBILITY_SCOPES
                ],
                "can_set_private_visibility": include_private,
                "rules": [
                    {"label": "Public", "description": "Anyone can see it."},
                    {"label": "Players", "description": "Only the DM and players in the campaign can see it."},
                    {"label": "DM", "description": "Only the campaign DM can see it."},
                    {"label": "Private", "description": "Only an app admin can see it."},
                ],
                "notes": [
                    "Campaign-level visibility acts as a floor for every campaign section.",
                    "Systems also apply source-level and article-level access rules on top of the Systems scope.",
                ]
                + (
                    []
                    if include_private
                    else ["Private visibility is reserved for admins even though admins can still access everything."]
                ),
                "links": {
                    "flask_control_url": url_for("campaign_control_panel_view", campaign_slug=campaign_slug),
                    "gen2_control_url": gen2_campaign_href(campaign_slug, "control"),
                },
            }
        )

    @api.patch("/campaigns/<campaign_slug>/control/visibility")
    @api_campaign_visibility_management_required
    def campaign_control_update_visibility(campaign_slug: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        raw_visibility = payload.get("visibility")
        if not isinstance(raw_visibility, dict):
            return json_error("Visibility settings must be provided as an object.", 400, code="validation_error")

        auth_store_instance = get_auth_store()
        changed_scopes: list[str] = []
        for scope in CAMPAIGN_VISIBILITY_SCOPES:
            current_visibility = auth_store_instance.get_campaign_visibility_setting(campaign_slug, scope)
            default_visibility = get_campaign_default_scope_visibility(campaign_slug, scope)
            selected_visibility = normalize_visibility_choice(
                str(
                    raw_visibility.get(
                        scope,
                        current_visibility.visibility if current_visibility is not None else default_visibility,
                    )
                    or ""
                )
            )
            if not is_valid_visibility(selected_visibility):
                return json_error(
                    f"Choose a valid visibility for {CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope]}.",
                    400,
                    code="validation_error",
                )
            if selected_visibility == VISIBILITY_PRIVATE and not user.is_admin:
                return json_error("Private visibility is reserved for app admins.", 400, code="validation_error")

            if current_visibility is not None and current_visibility.visibility == selected_visibility:
                continue
            if current_visibility is None and default_visibility == selected_visibility:
                continue

            auth_store_instance.upsert_campaign_visibility_setting(
                campaign_slug,
                scope,
                visibility=selected_visibility,
                updated_by_user_id=user.id,
            )
            auth_store_instance.write_audit_event(
                event_type="campaign_visibility_updated",
                actor_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "scope": scope,
                    "visibility": selected_visibility,
                    "source": "campaign_control_api",
                },
            )
            changed_scopes.append(CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope])

        clear_campaign_visibility_cache(campaign_slug)
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "visibility_rows": [
                    serialize_campaign_control_visibility_row(campaign_slug, scope)
                    for scope in CAMPAIGN_VISIBILITY_SCOPES
                ],
                "changed_scopes": changed_scopes,
                "message": (
                    f"Updated visibility for {', '.join(changed_scopes)}."
                    if changed_scopes
                    else "Visibility settings already matched those values."
                ),
            }
        )

    @api.get("/campaigns/<campaign_slug>/help")
    @api_campaign_scope_access_required("campaign")
    def campaign_help(campaign_slug: str):
        builder = current_app.extensions.get("campaign_help_context_builder")
        if not callable(builder):
            return json_error("Campaign Help is not available.", 500, code="server_error")

        context = builder(campaign_slug)
        campaign = context.get("campaign")
        if campaign is None:
            abort(404)
        available_labels = context.get("help_available_surface_labels")
        cross_cutting_limits = context.get("help_cross_cutting_limits")
        visibility_rows = context.get("help_visibility_rows")
        help_surfaces = context.get("help_surfaces")
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "viewer_role_label": str(context.get("help_viewer_role_label") or ""),
                "viewer_role_summary": str(context.get("help_viewer_role_summary") or ""),
                "campaign_system_label": str(context.get("help_campaign_system_label") or ""),
                "is_authenticated": get_current_user() is not None,
                "available_surface_labels": [
                    str(label).strip()
                    for label in available_labels
                    if str(label).strip()
                ]
                if isinstance(available_labels, list)
                else [],
                "cross_cutting_limits": [
                    str(item).strip()
                    for item in cross_cutting_limits
                    if str(item).strip()
                ]
                if isinstance(cross_cutting_limits, list)
                else [],
                "visibility_rows": [
                    serialize_campaign_help_visibility_row(row)
                    for row in visibility_rows
                ]
                if isinstance(visibility_rows, list)
                else [],
                "surfaces": [
                    serialize_campaign_help_surface(surface)
                    for surface in help_surfaces
                ]
                if isinstance(help_surfaces, list)
                else [],
                "account_note": str(context.get("help_account_note") or ""),
                "links": {
                    "flask_help_url": url_for("campaign_help_view", campaign_slug=campaign_slug),
                    "gen2_help_url": gen2_campaign_href(campaign_slug, "help"),
                    "account_url": "/app-next/account",
                    "flask_account_url": url_for("account_settings_view"),
                    "sign_in_url": url_for("sign_in", next=url_for("campaign_help_view", campaign_slug=campaign_slug)),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/wiki")
    @api_campaign_scope_access_required("campaign")
    def campaign_wiki_home(campaign_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        wiki_visibility = get_effective_campaign_visibility(campaign_slug, "wiki")
        wiki_visibility_label = VISIBILITY_LABELS.get(wiki_visibility, wiki_visibility)
        can_view_wiki = can_access_campaign_scope(campaign_slug, "wiki")
        frontend_mode = normalize_frontend_mode(get_current_user_preferences().frontend_mode)
        query = request.args.get("q", "").strip() if can_view_wiki else ""
        grouped_sections: list[dict[str, Any]] = []
        navigation_pages: list[Any] = []
        result_count = 0
        overview_page = None

        if can_view_wiki:
            navigation_pages = repository.search_pages(campaign_slug, "")
            pages = navigation_pages if not query else repository.search_pages(campaign_slug, query)
            grouped_pages_map: dict[str, list[Any]] = defaultdict(list)
            for page in pages:
                grouped_pages_map[page.section].append(page)
            grouped_sections = [
                serialize_public_wiki_section_group(
                    campaign,
                    section_name,
                    grouped_pages_map[section_name],
                    frontend_mode=frontend_mode,
                )
                for section_name in sorted(grouped_pages_map, key=section_sort_key)
            ]
            result_count = len(pages)
            if not query:
                overview_pages = grouped_pages_map.get("Overview", [])
                if overview_pages:
                    body_html = repository.get_page_body_html(campaign_slug, overview_pages[0].route_slug)
                    if body_html is not None:
                        overview_page = serialize_public_wiki_page_with_body(
                            campaign,
                            overview_pages[0],
                            body_html,
                            frontend_mode=frontend_mode,
                        )

        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "frontend_mode": frontend_mode,
                "can_view_wiki": can_view_wiki,
                "wiki_visibility_label": wiki_visibility_label,
                "query": query,
                "result_count": result_count,
                "grouped_sections": grouped_sections,
                "overview_page": overview_page,
                "message": (
                    f"The player wiki for this campaign currently requires {wiki_visibility_label} access."
                    if not can_view_wiki
                    else ""
                ),
                "section_navigation": (
                    serialize_public_wiki_section_navigation(
                        campaign,
                        navigation_pages,
                        frontend_mode=frontend_mode,
                    )
                    if can_view_wiki
                    else []
                ),
                "links": {
                    "flask_campaign_url": url_for("campaign_view", campaign_slug=campaign.slug),
                    "campaign_url": preferred_campaign_href(campaign.slug, frontend_mode=frontend_mode),
                    "gen2_campaign_url": gen2_campaign_href(campaign.slug),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/wiki/sections/<section_slug>")
    @api_campaign_scope_access_required("wiki")
    def campaign_wiki_section(campaign_slug: str, section_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        pages = repository.get_section_pages(campaign_slug, section_slug)
        if not pages:
            abort(404)

        frontend_mode = normalize_frontend_mode(get_current_user_preferences().frontend_mode)
        section_name = pages[0].section
        navigation_pages = repository.search_pages(campaign_slug, "")
        split_pages = split_public_wiki_pages_by_subsection(
            campaign,
            section_name,
            pages,
            frontend_mode=frontend_mode,
        )
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "frontend_mode": frontend_mode,
                "section_name": section_name,
                "section_slug": section_slug,
                "page_count": len(pages),
                "pages": [
                    serialize_public_wiki_page(campaign, page, frontend_mode=frontend_mode)
                    for page in pages
                ],
                **split_pages,
                "section_navigation": serialize_public_wiki_section_navigation(
                    campaign,
                    navigation_pages,
                    frontend_mode=frontend_mode,
                ),
                "links": {
                    "flask_section_url": url_for(
                        "section_view",
                        campaign_slug=campaign.slug,
                        section_slug=section_slug,
                    ),
                    "campaign_url": preferred_campaign_href(campaign.slug, frontend_mode=frontend_mode),
                    "gen2_campaign_url": gen2_campaign_href(campaign.slug),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/wiki/pages/<path:page_slug>")
    @api_campaign_scope_access_required("wiki")
    def campaign_wiki_page(campaign_slug: str, page_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        page = repository.get_page(campaign_slug, page_slug)
        if page is None:
            abort(404)

        body_html = repository.get_page_body_html(campaign_slug, page_slug)
        if body_html is None:
            abort(404)

        backlinks = repository.get_backlinks(campaign_slug, page_slug)
        frontend_mode = normalize_frontend_mode(get_current_user_preferences().frontend_mode)
        navigation_pages = repository.search_pages(campaign_slug, "")
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "frontend_mode": frontend_mode,
                "page": serialize_public_wiki_page_with_body(
                    campaign,
                    page,
                    body_html,
                    frontend_mode=frontend_mode,
                ),
                "backlinks": [
                    serialize_public_wiki_page(campaign, backlink, frontend_mode=frontend_mode)
                    for backlink in backlinks
                ],
                "section_navigation": serialize_public_wiki_section_navigation(
                    campaign,
                    navigation_pages,
                    frontend_mode=frontend_mode,
                ),
                "links": {
                    "flask_page_url": url_for(
                        "page_view",
                        campaign_slug=campaign.slug,
                        page_slug=page.route_slug,
                    ),
                    "campaign_url": preferred_campaign_href(campaign.slug, frontend_mode=frontend_mode),
                    "section_url": preferred_campaign_href(
                        campaign.slug,
                        f"sections/{slugify(page.section)}",
                        frontend_mode=frontend_mode,
                    ),
                    "gen2_campaign_url": gen2_campaign_href(campaign.slug),
                    "gen2_section_url": gen2_campaign_href(campaign.slug, f"sections/{slugify(page.section)}"),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/content/config")
    @api_campaign_content_management_required
    def content_config_detail(campaign_slug: str):
        try:
            record = get_campaign_config_file(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
        except (CampaignContentError, FileNotFoundError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "config_file": serialize_campaign_config_record(record)})

    @api.patch("/campaigns/<campaign_slug>/content/config")
    @api_campaign_content_management_required
    def content_config_update(campaign_slug: str):
        try:
            payload = load_json_object()
            updates = payload.get("config", payload)
            record = update_campaign_config_file(
                current_app.config["CAMPAIGNS_DIR"],
                campaign_slug,
                updates=updates,
            )
        except (CampaignContentError, FileNotFoundError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refresh_repository_store()
        refreshed_record = get_campaign_config_file(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
        return jsonify({"ok": True, "config_file": serialize_campaign_config_record(refreshed_record or record)})

    @api.get("/campaigns/<campaign_slug>/content/assets")
    @api_campaign_content_management_required
    def content_asset_list(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        return jsonify(
            {
                "ok": True,
                "assets": [
                    serialize_asset_file_summary(campaign_slug, record)
                    for record in list_campaign_asset_files(campaign)
                ],
            }
        )

    @api.get("/campaigns/<campaign_slug>/content/assets/<path:asset_ref>")
    @api_campaign_content_management_required
    def content_asset_detail(campaign_slug: str, asset_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            record = get_campaign_asset_file_record(campaign, asset_ref)
        except CampaignContentError as exc:
            return json_error(str(exc), 400, code="validation_error")
        if record is None:
            abort(404)

        return jsonify({"ok": True, "asset_file": serialize_asset_file_record(campaign_slug, record, include_data=True)})

    @api.put("/campaigns/<campaign_slug>/content/assets/<path:asset_ref>")
    @api_campaign_content_management_required
    def content_asset_upsert(campaign_slug: str, asset_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            payload = load_json_object()
            asset_file = decode_embedded_file(payload.get("asset_file"), label="asset_file")
            record = write_campaign_asset_file(
                campaign,
                asset_ref,
                data_blob=asset_file["data_blob"],
            )
        except (CampaignContentError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "asset_file": serialize_asset_file_record(campaign_slug, record)})

    @api.delete("/campaigns/<campaign_slug>/content/assets/<path:asset_ref>")
    @api_campaign_content_management_required
    def content_asset_delete(campaign_slug: str, asset_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            deleted = delete_campaign_asset_file(campaign, asset_ref)
        except CampaignContentError as exc:
            return json_error(str(exc), 400, code="validation_error")
        if deleted is None:
            abort(404)

        return jsonify(
            {
                "ok": True,
                "deleted": {
                    "asset_ref": deleted.asset_ref,
                    "relative_path": deleted.relative_path,
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/content/pages")
    @api_campaign_content_management_required
    def content_page_list(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        page_records = list_campaign_page_files(
            campaign,
            page_store=get_campaign_page_store(),
        )
        removal_safety = _build_content_page_removal_safety(
            campaign_slug,
            campaign,
            page_records,
        )
        return jsonify(
            {
                "ok": True,
                "pages": [
                    _build_content_page_file_payload(
                        campaign_slug,
                        record,
                        removal_safety=removal_safety.get(record.page_ref),
                    )
                    for record in page_records
                ],
            }
        )

    @api.get("/campaigns/<campaign_slug>/content/pages/<path:page_ref>")
    @api_campaign_content_management_required
    def content_page_detail(campaign_slug: str, page_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except CampaignContentError as exc:
            return json_error(str(exc), 400, code="validation_error")
        if record is None:
            abort(404)

        page_records = list_campaign_page_files(
            campaign,
            page_store=get_campaign_page_store(),
        )
        removal_safety = _build_content_page_removal_safety(
            campaign_slug,
            campaign,
            page_records,
        )
        return jsonify(
            {
                "ok": True,
                "page_file": _build_content_page_file_payload(
                    campaign_slug,
                    record,
                    removal_safety=removal_safety.get(record.page_ref),
                    include_body=True,
                ),
            }
        )

    @api.put("/campaigns/<campaign_slug>/content/pages/<path:page_ref>")
    @api_campaign_content_management_required
    def content_page_upsert(campaign_slug: str, page_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            payload = load_json_object()
            record = write_campaign_page_file(
                campaign,
                page_ref,
                metadata=payload.get("metadata", {}),
                body_markdown=payload.get("body_markdown", ""),
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        refresh_repository_store()
        refreshed_record = get_campaign_page_file(
            campaign,
            page_ref,
            page_store=get_campaign_page_store(),
        )
        if refreshed_record is None:
            refreshed_record = record
        page_records = list_campaign_page_files(
            campaign,
            page_store=get_campaign_page_store(),
        )
        removal_safety = _build_content_page_removal_safety(
            campaign_slug,
            campaign,
            page_records,
        )
        return jsonify(
            {
                "ok": True,
                "page_file": _build_content_page_file_payload(
                    campaign_slug,
                    refreshed_record,
                    removal_safety=removal_safety.get(refreshed_record.page_ref),
                    include_body=True,
                ),
            }
        )

    @api.delete("/campaigns/<campaign_slug>/content/pages/<path:page_ref>")
    @api_campaign_content_management_required
    def content_page_delete(campaign_slug: str, page_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            existing_record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except CampaignContentError as exc:
            return json_error(str(exc), 400, code="validation_error")
        if existing_record is None:
            abort(404)

        page_records = list_campaign_page_files(
            campaign,
            page_store=get_campaign_page_store(),
        )
        removal_safety = _build_content_page_removal_safety(
            campaign_slug,
            campaign,
            page_records,
        )
        page_safety = removal_safety.get(existing_record.page_ref, {})

        try:
            request_payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")
        force = _parse_force_delete_flag() or _parse_force_delete_payload(request_payload)

        if page_safety and not force and not page_safety.get("can_hard_delete", True):
            return json_error(
                "Hard delete blocked for this content page.",
                409,
                code="hard_delete_blocked",
                details={
                    "page_ref": existing_record.page_ref,
                    "removal_safety": page_safety,
                    "force_query_param": "force",
                    "force_required": True,
                },
            )

        try:
            deleted = delete_campaign_page_file(
                campaign,
                existing_record.page_ref,
                page_store=get_campaign_page_store(),
            )
        except CampaignContentError as exc:
            return json_error(str(exc), 400, code="validation_error")
        if deleted is None:
            abort(404)

        refresh_repository_store()
        return jsonify(
            {
                "ok": True,
                "deleted": {
                    "page_ref": deleted.page_ref,
                    "relative_path": deleted.relative_path,
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/content/characters")
    @api_campaign_content_management_required
    def content_character_list(campaign_slug: str):
        try:
            records = list_campaign_character_files(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
        except (CampaignContentError, FileNotFoundError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "characters": [serialize_character_file_summary(record) for record in records],
            }
        )

    @api.get("/campaigns/<campaign_slug>/content/characters/<character_slug>")
    @api_campaign_content_management_required
    def content_character_detail(campaign_slug: str, character_slug: str):
        try:
            record = get_campaign_character_file(current_app.config["CAMPAIGNS_DIR"], campaign_slug, character_slug)
        except (CampaignContentError, FileNotFoundError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")
        if record is None:
            abort(404)

        return jsonify({"ok": True, "character_file": serialize_character_file_record(record)})

    @api.put("/campaigns/<campaign_slug>/content/characters/<character_slug>")
    @api_campaign_content_management_required
    def content_character_upsert(campaign_slug: str, character_slug: str):
        try:
            payload = load_json_object()
            record = write_campaign_character_file(
                current_app.config["CAMPAIGNS_DIR"],
                campaign_slug,
                character_slug,
                definition_payload=payload.get("definition"),
                import_metadata_payload=payload.get("import_metadata"),
                state_store=current_app.extensions["character_state_store"],
            )
        except (CampaignContentError, FileNotFoundError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "character_file": serialize_character_file_record(record)})

    @api.delete("/campaigns/<campaign_slug>/content/characters/<character_slug>")
    @api_campaign_content_management_required
    def content_character_delete(campaign_slug: str, character_slug: str):
        try:
            deleted = delete_campaign_character_file(
                current_app.config["CAMPAIGNS_DIR"],
                campaign_slug,
                character_slug,
                state_store=current_app.extensions["character_state_store"],
                auth_store=current_app.extensions["auth_store"],
            )
        except (CampaignContentError, FileNotFoundError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")
        if deleted is None:
            abort(404)

        return jsonify(
            {
                "ok": True,
                "deleted": {
                    "character_slug": deleted.character_slug,
                    "deleted_files": deleted.deleted_files,
                    "deleted_state": deleted.deleted_state,
                    "deleted_assignment": deleted.deleted_assignment,
                    "deleted_assets": deleted.deleted_assets,
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/systems")
    @api.get("/campaigns/<campaign_slug>/systems/search")
    @api_campaign_scope_access_required("systems")
    def systems_index(campaign_slug: str):
        query = request.args.get("q", "").strip()
        reference_query = request.args.get("reference_q", "").strip()
        return jsonify(
            {
                "ok": True,
                **build_systems_index_payload(
                    campaign_slug,
                    query=query,
                    reference_query=reference_query,
                ),
            }
        )

    @api.get("/campaigns/<campaign_slug>/systems/sources")
    @api_campaign_scope_access_required("systems")
    def systems_source_list(campaign_slug: str):
        systems_service = current_app.extensions["systems_service"]
        source_states = systems_service.list_campaign_source_states(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            source_states = [
                state
                for state in source_states
                if state.is_enabled and can_access_campaign_systems_source(campaign_slug, state.source.source_id)
            ]

        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(get_repository().get_campaign(campaign_slug)),
                "library": serialize_systems_library(systems_service.get_campaign_library(campaign_slug)),
                "sources": [serialize_systems_source_state(campaign_slug, state) for state in source_states],
                "permissions": {
                    "can_manage_systems": can_manage_campaign_systems(campaign_slug),
                },
            }
        )

    @api.put("/campaigns/<campaign_slug>/systems/sources")
    @api_campaign_systems_management_required
    @api_login_required
    def systems_source_update(campaign_slug: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            changed_sources = current_app.extensions["systems_service"].update_campaign_sources(
                campaign_slug,
                updates=list(payload.get("updates") or []),
                actor_user_id=user.id,
                acknowledge_proprietary=bool(payload.get("acknowledge_proprietary")),
                can_set_private=bool(user.is_admin),
            )
        except (SystemsPolicyValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        auth_store = get_auth_store()
        systems_service = current_app.extensions["systems_service"]
        for source in changed_sources:
            state = systems_service.get_campaign_source_state(campaign_slug, source.source_id)
            if state is None:
                continue
            auth_store.write_audit_event(
                event_type="campaign_systems_source_updated",
                actor_user_id=user.id,
                campaign_slug=campaign_slug,
                metadata={
                    "library_slug": source.library_slug,
                    "source_id": source.source_id,
                    "visibility": state.default_visibility,
                    "is_enabled": state.is_enabled,
                    "source": "api",
                },
            )

        return jsonify(
            {
                "ok": True,
                "sources": [
                    serialize_systems_source_state(campaign_slug, state)
                    for state in systems_service.list_campaign_source_states(campaign_slug)
                ],
            }
        )

    @api.get("/campaigns/<campaign_slug>/systems/sources/<source_id>")
    @api_campaign_systems_source_access_required
    def systems_source_detail(campaign_slug: str, source_id: str):
        systems_service = current_app.extensions["systems_service"]
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)

        book_entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            entry_type="book",
            limit=None,
        )
        all_entry_groups = []
        for entry_type, _ in systems_service.list_entry_type_counts_for_campaign_source(campaign_slug, source_id):
            accessible_entries = list_accessible_campaign_source_entries(
                campaign_slug,
                source_id,
                entry_type=entry_type,
                limit=None,
            )
            if not accessible_entries:
                continue
            all_entry_groups.append(
                {
                    "entry_type": entry_type,
                    "entry_type_label": systems_entry_type_label(entry_type),
                    "count": len(accessible_entries),
                }
            )
        all_entry_groups.sort(
            key=lambda item: (
                item["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
                *systems_entry_type_sort_key(item["entry_type"]),
            )
        )
        entry_groups = [
            item for item in all_entry_groups if item["entry_type"] not in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        ]
        raw_rules_reference_entries = systems_service.list_rules_reference_entries_for_campaign(
            campaign_slug,
            include_source_ids=[source_id],
            limit=None,
        )
        rules_reference_entries = filter_accessible_systems_entries(
            campaign_slug,
            raw_rules_reference_entries,
        )
        has_book_rules_reference_entries = any(entry.entry_type == "book" for entry in rules_reference_entries)
        has_rule_rules_reference_entries = any(entry.entry_type == "rule" for entry in rules_reference_entries)
        if has_book_rules_reference_entries and has_rule_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's book chapters and rules entries using curated metadata like chapter "
                "labels, section headings, aliases, formulas, and rule facets. It does not search full entry body text."
            )
        elif has_book_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's book chapters using curated metadata like chapter labels and section "
                "headings. It does not search full entry body text."
            )
        elif has_rule_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's rules entries using curated metadata like aliases, formulas, and rule "
                "facets. It does not search full entry body text."
            )
        else:
            rules_reference_search_meta = ""
        rules_reference_scope = systems_service.get_rules_reference_search_scope_for_source(state.source)
        rules_reference_scope_note = (
            "This DM-heavy source keeps chapter browse and rules-reference metadata search on this source page instead "
            "of surfacing those chapter matches in the landing-page Rules Reference Search."
            if rules_reference_entries and rules_reference_scope == "source_only"
            else ""
        )
        reference_query = request.args.get("reference_q", "").strip()
        rules_reference_results = (
            [
                serialize_systems_rules_reference_result(entry)
                for entry in filter_accessible_systems_entries(
                    campaign_slug,
                    systems_service.search_rules_reference_entries_for_campaign(
                        campaign_slug,
                        query=reference_query,
                        include_source_ids=[source_id],
                        limit=None,
                    ),
                    limit=100,
                )
            ]
            if reference_query
            else []
        )

        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(get_repository().get_campaign(campaign_slug)),
                "source": serialize_systems_source_state(campaign_slug, state),
                "entry_groups": entry_groups,
                "book_entries": [serialize_systems_entry_summary(entry) for entry in book_entries],
                "entry_count": sum(item["count"] for item in all_entry_groups),
                "browsable_entry_count": sum(item["count"] for item in entry_groups),
                "hidden_entry_types": [
                    item["entry_type"] for item in all_entry_groups if item["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
                ],
                "has_rules_reference_search": bool(rules_reference_entries),
                "rules_reference_search_meta": rules_reference_search_meta,
                "rules_reference_scope_note": rules_reference_scope_note,
                "reference_query": reference_query,
                "rules_reference_results": rules_reference_results,
                "book_visibility_policy_note": (
                    systems_service.get_book_entry_policy_note_for_source(state.source)
                    if book_entries
                    else ""
                ),
                "permissions": {
                    "can_manage_systems": can_manage_campaign_systems(campaign_slug),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>")
    @api_campaign_systems_source_access_required
    def systems_source_category_detail(campaign_slug: str, source_id: str, entry_type: str):
        systems_service = current_app.extensions["systems_service"]
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)

        normalized_entry_type = str(entry_type or "").strip().lower()
        if not normalized_entry_type:
            abort(404)

        all_entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            entry_type=normalized_entry_type,
            limit=None,
        )
        entry_count = len(all_entries)
        if entry_count <= 0:
            abort(404)

        query = request.args.get("q", "").strip()
        entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            entry_type=normalized_entry_type,
            query=query,
            limit=None,
        )

        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(get_repository().get_campaign(campaign_slug)),
                "source": serialize_systems_source_state(campaign_slug, state),
                "entry_type": normalized_entry_type,
                "entry_type_label": systems_entry_type_label(normalized_entry_type),
                "query": query,
                "entry_count": entry_count,
                "filtered_entry_count": len(entries),
                "entries": [serialize_systems_entry_summary(entry) for entry in entries],
                "permissions": {
                    "can_manage_systems": can_manage_campaign_systems(campaign_slug),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/systems/entries/<entry_slug>")
    @api_campaign_systems_entry_access_required
    def systems_entry_detail(campaign_slug: str, entry_slug: str):
        entry = current_app.extensions["systems_service"].get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
        if entry is None:
            abort(404)

        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(get_repository().get_campaign(campaign_slug)),
                "entry": serialize_systems_entry_record(campaign_slug, entry),
                "permissions": {
                    "can_manage_systems": can_manage_campaign_systems(campaign_slug),
                },
                "links": {
                    "flask_entry_url": url_for(
                        "campaign_systems_entry_detail",
                        campaign_slug=campaign_slug,
                        entry_slug=entry.slug,
                    ),
                    "flask_source_url": url_for(
                        "campaign_systems_source_detail",
                        campaign_slug=campaign_slug,
                        source_id=entry.source_id,
                    ),
                    "flask_source_category_url": url_for(
                        "campaign_systems_source_type_detail",
                        campaign_slug=campaign_slug,
                        source_id=entry.source_id,
                        entry_type=entry.entry_type,
                    ),
                    "dm_content_systems_url": (
                        url_for(
                            "campaign_dm_content_subpage_view",
                            campaign_slug=campaign_slug,
                            dm_content_subpage="systems",
                            entry_key=entry.entry_key,
                            _anchor="systems-entry-overrides",
                        )
                        if can_manage_campaign_systems(campaign_slug)
                        else ""
                    ),
                },
            }
        )

    @api.put("/campaigns/<campaign_slug>/systems/overrides/<path:entry_key>")
    @api_campaign_systems_management_required
    @api_login_required
    def systems_entry_override_update(campaign_slug: str, entry_key: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            visibility_override = payload.get("visibility_override")
            is_enabled_override = payload.get("is_enabled_override")
            if is_enabled_override is not None:
                is_enabled_override = coerce_bool(is_enabled_override, label="is_enabled_override")
            override = current_app.extensions["systems_service"].update_campaign_entry_override(
                campaign_slug,
                entry_key=entry_key,
                visibility_override=(
                    str(visibility_override).strip() if visibility_override not in (None, "") else None
                ),
                is_enabled_override=is_enabled_override,
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except (SystemsPolicyValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        get_auth_store().write_audit_event(
            event_type="campaign_systems_entry_override_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": override.entry_key,
                "visibility": override.visibility_override or "inherit",
                "source": "api",
            },
        )

        entry = current_app.extensions["systems_service"].get_entry_for_campaign(campaign_slug, entry_key)
        return jsonify(
            {
                "ok": True,
                "override": {
                    "entry_key": override.entry_key,
                    "visibility_override": override.visibility_override,
                    "is_enabled_override": override.is_enabled_override,
                    "updated_at": serialize_datetime(override.updated_at),
                    "updated_by_user_id": override.updated_by_user_id,
                },
                "entry": serialize_systems_entry_record(campaign_slug, entry) if entry is not None else None,
            }
        )

    @api.get("/campaigns/<campaign_slug>/session")
    @api_campaign_scope_access_required("session")
    def session_state(campaign_slug: str):
        session_service = current_app.extensions["campaign_session_service"]
        live_revision = session_service.get_live_revision(campaign_slug)
        live_view_token = build_session_live_view_token(campaign_slug, "session")
        if should_short_circuit_live_session(
            live_revision=live_revision,
            live_view_token=live_view_token,
        ):
            return jsonify(
                {
                    "ok": True,
                    "changed": False,
                    "session_revision": live_revision,
                    "session_view_token": live_view_token,
                }
            )

        payload = build_session_payload(campaign_slug)
        payload["session_revision"] = live_revision
        payload["session_view_token"] = live_view_token
        return jsonify({"ok": True, **payload})

    @api.get("/campaigns/<campaign_slug>/session/article-sources/search")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_article_source_search(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "ok": True,
                    "results": [],
                    "message": "Type at least 2 letters to search published wiki pages and Systems entries.",
                }
            )

        results = build_session_article_source_search_results(campaign_slug, query, limit=30)
        message = (
            "Showing the first 30 matching articles."
            if len(results) == 30
            else (
                f"Found {len(results)} matching article{'s' if len(results) != 1 else ''}."
                if results
                else "No published wiki or Systems articles matched that search."
            )
        )
        return jsonify({"ok": True, "results": results, "message": message})

    @api.get("/campaigns/<campaign_slug>/session/articles/<int:article_id>/image")
    @api_campaign_scope_access_required("session")
    def session_article_image(campaign_slug: str, article_id: int):
        session_service = current_app.extensions["campaign_session_service"]
        article = session_service.get_article(campaign_slug, article_id)
        image = session_service.get_article_image(campaign_slug, article_id)
        if article is None or image is None:
            abort(404)

        if not can_manage_campaign_session(campaign_slug):
            active_session = session_service.get_active_session(campaign_slug)
            if (
                active_session is None
                or not article.is_revealed
                or article.revealed_in_session_id != active_session.id
            ):
                abort(404)

        return send_file(
            BytesIO(image.data_blob),
            mimetype=image.media_type,
            download_name=image.filename,
        )

    @api.post("/campaigns/<campaign_slug>/session/start")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_start(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            session_record = current_app.extensions["campaign_session_service"].begin_session(
                campaign_slug,
                started_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "session": serialize_session_record(session_record)})

    @api.post("/campaigns/<campaign_slug>/session/close")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_close(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            session_record = current_app.extensions["campaign_session_service"].close_session(
                campaign_slug,
                ended_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "session": serialize_session_record(session_record)})

    @api.get("/campaigns/<campaign_slug>/session/logs/<int:session_id>")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_log_detail(campaign_slug: str, session_id: int):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        session_service = current_app.extensions["campaign_session_service"]
        session_record = session_service.get_session_log(campaign_slug, session_id)
        if session_record is None or session_record.is_active:
            abort(404)

        articles = session_service.list_articles(campaign_slug)
        article_lookup = {article.id: article for article in articles}
        article_images = session_service.list_article_images(list(article_lookup)) if article_lookup else {}

        return jsonify(
            {
                "ok": True,
                "session": serialize_session_record(session_record),
                "messages": [
                    serialize_session_message(campaign_slug, message, article_lookup, article_images)
                    for message in session_service.list_messages(
                        session_record.id,
                        can_manage_session=True,
                    )
                ],
            }
        )

    @api.delete("/campaigns/<campaign_slug>/session/logs/<int:session_id>")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_log_delete(campaign_slug: str, session_id: int):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        try:
            current_app.extensions["campaign_session_service"].delete_session_log(campaign_slug, session_id)
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "deleted_session_id": session_id})

    @api.post("/campaigns/<campaign_slug>/session/messages")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_message_create(campaign_slug: str):
        if not can_post_campaign_session_messages(campaign_slug):
            return json_error("You do not have permission to post session messages.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        try:
            message = current_app.extensions["campaign_session_service"].post_message(
                campaign_slug,
                body_text=payload.get("body", ""),
                author_display_name=user.display_name,
                author_user_id=user.id,
                recipient_scope=str(payload.get("recipient_scope", "global")),
                recipient_user_id=payload.get("recipient_user_id"),
            )
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "message": serialize_session_message(campaign_slug, message, {}, {}),
            }
        )

    @api.post("/campaigns/<campaign_slug>/session/articles")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_article_create(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        session_service = current_app.extensions["campaign_session_service"]
        article = None
        mode = str(payload.get("mode") or "manual").strip().lower()
        if mode not in {"manual", "upload", "wiki"}:
            return json_error("Article mode must be 'manual', 'upload', or 'wiki'.", 400, code="validation_error")

        try:
            if mode == "upload":
                filename = str(payload.get("filename") or "").strip()
                markdown_text = str(payload.get("markdown_text") or "")
                markdown_upload = session_service.parse_article_markdown_upload(
                    filename=filename,
                    data_blob=markdown_text.encode("utf-8"),
                )
                image_payload = payload.get("referenced_image")
                if markdown_upload.image_reference and image_payload is None:
                    raise CampaignSessionValidationError(
                        "This markdown file references an image. Include referenced_image too."
                    )
                referenced_image_upload = None
                if image_payload is not None:
                    image_file = decode_embedded_file(image_payload, label="referenced_image")
                    referenced_image_upload = session_service.prepare_article_image_upload(
                        filename=image_file["filename"],
                        media_type=image_file["media_type"],
                        data_blob=image_file["data_blob"],
                        alt_text=markdown_upload.image_alt,
                        caption=markdown_upload.image_caption,
                    )
                article = session_service.create_article(
                    campaign_slug,
                    title=markdown_upload.title,
                    body_markdown=markdown_upload.body_markdown,
                    has_content_image=referenced_image_upload is not None,
                    created_by_user_id=user.id,
                )
                if referenced_image_upload is not None:
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=referenced_image_upload.filename,
                        media_type=referenced_image_upload.media_type,
                        data_blob=referenced_image_upload.data_blob,
                        alt_text=referenced_image_upload.alt_text,
                        caption=referenced_image_upload.caption,
                    )
            elif mode == "wiki":
                campaign = get_repository().get_campaign(campaign_slug)
                if campaign is None:
                    abort(404)

                source_kind, source_ref = parse_session_article_source_ref(
                    str(payload.get("source_ref") or payload.get("page_ref") or "")
                )
                if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
                    entry = get_pullable_session_systems_entry(campaign_slug, source_ref)
                    if entry is None:
                        raise CampaignSessionValidationError(
                            "Choose a visible published wiki page or Systems entry before pulling it into the session store."
                        )

                    source_body_html = entry.rendered_html.strip() or str(
                        ((entry.body or {}).get("rendered") or {}).get("summary_html") or ""
                    ).strip()
                    if not source_body_html:
                        raise CampaignSessionValidationError(
                            "The selected Systems entry does not have rendered article content to pull into the session store."
                        )

                    article = session_service.create_article(
                        campaign_slug,
                        title=entry.title,
                        body_markdown=source_body_html,
                        source_page_ref=build_session_article_systems_source_ref(entry.slug),
                        created_by_user_id=user.id,
                    )
                else:
                    page_record = get_pullable_session_wiki_page_record(
                        campaign,
                        source_ref,
                        include_body=True,
                    )
                    if page_record is None:
                        raise CampaignSessionValidationError(
                            "Choose a visible published wiki page or Systems entry before pulling it into the session store."
                        )

                    page_image_upload = None
                    if page_record.page.image_path:
                        image_path = get_campaign_asset_file(campaign, page_record.page.image_path)
                        if image_path is not None:
                            page_image_upload = session_service.prepare_article_image_upload(
                                filename=image_path.name,
                                media_type=guess_campaign_asset_media_type(image_path),
                                data_blob=image_path.read_bytes(),
                                alt_text=page_record.page.image_alt,
                                caption=page_record.page.image_caption,
                            )

                    source_body_markdown = page_record.body_markdown.strip() or page_record.page.summary.strip()
                    if not source_body_markdown and page_image_upload is None:
                        raise CampaignSessionValidationError(
                            "The selected wiki page does not have any body text, summary, or image to pull into the session store."
                        )
                    article = session_service.create_article(
                        campaign_slug,
                        title=page_record.page.title,
                        body_markdown=source_body_markdown,
                        source_page_ref=build_session_article_page_source_ref(page_record.page_ref),
                        has_content_image=page_image_upload is not None,
                        created_by_user_id=user.id,
                    )
                    if page_image_upload is not None:
                        session_service.attach_article_image(
                            campaign_slug,
                            article.id,
                            filename=page_image_upload.filename,
                            media_type=page_image_upload.media_type,
                            data_blob=page_image_upload.data_blob,
                            alt_text=page_image_upload.alt_text,
                            caption=page_image_upload.caption,
                        )
            else:
                image_payload = payload.get("image")
                manual_image_upload = None
                if image_payload is not None:
                    image_file = decode_embedded_file(image_payload, label="image")
                    manual_image_upload = session_service.prepare_article_image_upload(
                        filename=image_file["filename"],
                        media_type=image_file["media_type"],
                        data_blob=image_file["data_blob"],
                        alt_text=str(image_payload.get("alt_text") or "").strip(),
                        caption=str(image_payload.get("caption") or "").strip(),
                    )
                article = session_service.create_article(
                    campaign_slug,
                    title=payload.get("title", ""),
                    body_markdown=payload.get("body_markdown", ""),
                    has_content_image=manual_image_upload is not None,
                    created_by_user_id=user.id,
                )
                if manual_image_upload is not None:
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=manual_image_upload.filename,
                        media_type=manual_image_upload.media_type,
                        data_blob=manual_image_upload.data_blob,
                        alt_text=manual_image_upload.alt_text,
                        caption=manual_image_upload.caption,
                    )
        except (CampaignSessionValidationError, ValueError) as exc:
            if article is not None:
                try:
                    session_service.delete_article(campaign_slug, article.id)
                except CampaignSessionValidationError:
                    pass
            return json_error(str(exc), 400, code="validation_error")

        article_image = session_service.get_article_image(campaign_slug, article.id)
        return jsonify(
            {
                "ok": True,
                "article": serialize_session_article(campaign_slug, article, article_image),
            }
        )

    @api.put("/campaigns/<campaign_slug>/session/articles/<int:article_id>")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_article_update(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        session_service = current_app.extensions["campaign_session_service"]
        try:
            image_payload = payload.get("image")
            image_upload = None
            if image_payload is not None:
                image_file = decode_embedded_file(image_payload, label="image")
                image_upload = session_service.prepare_article_image_upload(
                    filename=image_file["filename"],
                    media_type=image_file["media_type"],
                    data_blob=image_file["data_blob"],
                    alt_text=str(image_payload.get("alt_text") or "").strip(),
                    caption=str(image_payload.get("caption") or "").strip(),
                )
            existing_image = session_service.get_article_image(campaign_slug, article_id)
            has_image = image_upload is not None or existing_image is not None
            article = session_service.update_article(
                campaign_slug,
                article_id,
                title=str(payload.get("title") or ""),
                body_markdown=str(payload.get("body_markdown") or ""),
                has_content_image=has_image,
                updated_by_user_id=user.id,
            )
            if image_upload is not None:
                session_service.attach_article_image(
                    campaign_slug,
                    article.id,
                    filename=image_upload.filename,
                    media_type=image_upload.media_type,
                    data_blob=image_upload.data_blob,
                    alt_text=image_upload.alt_text,
                    caption=image_upload.caption,
                    updated_by_user_id=user.id,
                )
            elif payload.get("image_alt_text") is not None or payload.get("image_caption") is not None:
                session_service.update_article_image_metadata(
                    campaign_slug,
                    article.id,
                    alt_text=str(payload.get("image_alt_text") or ""),
                    caption=str(payload.get("image_caption") or ""),
                    updated_by_user_id=user.id,
                )
        except (CampaignSessionValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        article_image = session_service.get_article_image(campaign_slug, article.id)
        return jsonify(
            {
                "ok": True,
                "article": serialize_session_article(campaign_slug, article, article_image),
            }
        )

    @api.post("/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_article_reveal(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            article, message = current_app.extensions["campaign_session_service"].reveal_article(
                campaign_slug,
                article_id,
                revealed_by_user_id=user.id,
                author_display_name=user.display_name,
            )
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        article_image = current_app.extensions["campaign_session_service"].get_article_image(campaign_slug, article.id)
        return jsonify(
            {
                "ok": True,
                "article": serialize_session_article(campaign_slug, article, article_image),
                "message": {
                    "id": message.id,
                    "session_id": message.session_id,
                    "campaign_slug": message.campaign_slug,
                    "message_type": message.message_type,
                    "body_text": message.body_text,
                    "author_user_id": message.author_user_id,
                    "author_display_name": message.author_display_name,
                    "article_id": message.article_id,
                    "created_at": serialize_datetime(message.created_at),
                },
            }
        )

    @api.delete("/campaigns/<campaign_slug>/session/articles/<int:article_id>")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_article_delete(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        try:
            article = current_app.extensions["campaign_session_service"].delete_article(campaign_slug, article_id)
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "article": serialize_session_article(campaign_slug, article)})

    @api.delete("/campaigns/<campaign_slug>/session/articles/revealed")
    @api_campaign_scope_access_required("session")
    @api_login_required
    def session_revealed_articles_clear(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            return json_error("You do not have permission to manage this session.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            articles = current_app.extensions["campaign_session_service"].delete_revealed_articles(
                campaign_slug,
                updated_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "deleted_articles": [serialize_session_article(campaign_slug, article) for article in articles],
                "deleted_article_ids": [article.id for article in articles],
            }
        )

    @api.get("/campaigns/<campaign_slug>/dm-content")
    @api_campaign_scope_access_required("dm_content")
    def dm_content_state(campaign_slug: str):
        return jsonify({"ok": True, **build_dm_content_payload(campaign_slug)})

    @api.get("/campaigns/<campaign_slug>/dm-content/systems")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_systems_state(campaign_slug: str):
        try:
            payload = build_dm_content_systems_payload(campaign_slug)
        except PermissionError:
            return json_error("Authentication required.", 401, code="auth_required")
        except RuntimeError as exc:
            return json_error(str(exc), 403, code="forbidden")
        return jsonify({"ok": True, **payload})

    @api.post("/campaigns/<campaign_slug>/dm-content/statblocks")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_statblock_create(campaign_slug: str):
        if not can_manage_campaign_dm_content(campaign_slug):
            return json_error("You do not have permission to manage DM Content.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        try:
            statblock = current_app.extensions["campaign_dm_content_service"].create_statblock(
                campaign_slug,
                filename=str(payload.get("filename") or "").strip(),
                data_blob=str(payload.get("markdown_text") or "").encode("utf-8"),
                subsection=str(payload.get("subsection") or "").strip(),
                created_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "statblock": serialize_dm_statblock(statblock)})

    @api.put("/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_statblock_update(campaign_slug: str, statblock_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            return json_error("You do not have permission to manage DM Content.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        has_markdown_text = "markdown_text" in payload
        has_body_markdown = "body_markdown" in payload
        has_subsection = "subsection" in payload
        if not has_markdown_text and not has_body_markdown and not has_subsection:
            return json_error(
                "Provide markdown_text, body_markdown, or subsection to update a statblock.",
                400,
                code="validation_error",
            )

        body_value = None
        if has_markdown_text:
            body_value = payload.get("markdown_text")
        elif has_body_markdown:
            body_value = payload.get("body_markdown")
        body_markdown = str(body_value or "") if has_markdown_text or has_body_markdown else None
        subsection = str(payload.get("subsection") or "").strip() if has_subsection else None

        try:
            statblock = current_app.extensions["campaign_dm_content_service"].update_statblock(
                campaign_slug,
                statblock_id,
                body_markdown=body_markdown,
                subsection=subsection,
                updated_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "statblock": serialize_dm_statblock(statblock)})

    @api.delete("/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_statblock_delete(campaign_slug: str, statblock_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            return json_error("You do not have permission to manage DM Content.", 403, code="forbidden")

        try:
            statblock = current_app.extensions["campaign_dm_content_service"].delete_statblock(
                campaign_slug,
                statblock_id,
            )
        except CampaignDMContentValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "statblock": serialize_dm_statblock(statblock)})

    @api.post("/campaigns/<campaign_slug>/dm-content/conditions")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_condition_create(campaign_slug: str):
        if not can_manage_campaign_dm_content(campaign_slug):
            return json_error("You do not have permission to manage DM Content.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        try:
            definition = current_app.extensions["campaign_dm_content_service"].create_condition_definition(
                campaign_slug,
                name=payload.get("name", ""),
                description_markdown=payload.get("description_markdown", ""),
                created_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "condition": serialize_condition_definition(definition)})

    @api.put("/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_condition_update(campaign_slug: str, condition_definition_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            return json_error("You do not have permission to manage DM Content.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        has_name = "name" in payload
        has_description = "description_markdown" in payload
        if not has_name and not has_description:
            return json_error(
                "Provide name or description_markdown to update a custom condition.",
                400,
                code="validation_error",
            )

        try:
            definition = current_app.extensions["campaign_dm_content_service"].update_condition_definition(
                campaign_slug,
                condition_definition_id,
                name=str(payload.get("name") or "") if has_name else None,
                description_markdown=(
                    str(payload.get("description_markdown") or "") if has_description else None
                ),
                updated_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "condition": serialize_condition_definition(definition)})

    @api.delete("/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>")
    @api_campaign_scope_access_required("dm_content")
    @api_login_required
    def dm_content_condition_delete(campaign_slug: str, condition_definition_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            return json_error("You do not have permission to manage DM Content.", 403, code="forbidden")

        try:
            definition = current_app.extensions["campaign_dm_content_service"].delete_condition_definition(
                campaign_slug,
                condition_definition_id,
            )
        except CampaignDMContentValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, "condition": serialize_condition_definition(definition)})

    @api.post("/campaigns/<campaign_slug>/systems/custom-entries")
    @api_campaign_systems_management_required
    @api_login_required
    def systems_custom_entry_create(campaign_slug: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            entry = current_app.extensions["systems_service"].create_custom_campaign_entry(
                campaign_slug,
                title=str(payload.get("title") or ""),
                entry_type=str(payload.get("entry_type") or ""),
                slug_leaf=str(payload.get("slug_leaf") or ""),
                provenance=str(payload.get("provenance") or ""),
                visibility=str(payload.get("visibility") or ""),
                search_metadata=str(payload.get("search_metadata") or ""),
                body_markdown=str(payload.get("body_markdown") or ""),
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")
        except SystemsPolicyValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_created",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "source": "api",
            },
        )
        return jsonify(
            {
                "ok": True,
                "entry": serialize_custom_systems_entry(campaign_slug, entry),
                "systems": build_dm_content_systems_payload(campaign_slug),
            }
        )

    @api.put("/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>")
    @api_campaign_systems_management_required
    @api_login_required
    def systems_custom_entry_update(campaign_slug: str, entry_slug: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            entry = current_app.extensions["systems_service"].update_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                title=str(payload.get("title") or ""),
                entry_type=str(payload.get("entry_type") or ""),
                provenance=str(payload.get("provenance") or ""),
                visibility=str(payload.get("visibility") or ""),
                search_metadata=str(payload.get("search_metadata") or ""),
                body_markdown=str(payload.get("body_markdown") or ""),
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")
        except SystemsPolicyValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "source": "api",
            },
        )
        return jsonify(
            {
                "ok": True,
                "entry": serialize_custom_systems_entry(campaign_slug, entry),
                "systems": build_dm_content_systems_payload(campaign_slug),
            }
        )

    @api.post("/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/archive")
    @api_campaign_systems_management_required
    @api_login_required
    def systems_custom_entry_archive(campaign_slug: str, entry_slug: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            entry = current_app.extensions["systems_service"].archive_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                actor_user_id=user.id,
            )
        except SystemsPolicyValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_archived",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "source": "api",
            },
        )
        refreshed = current_app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            campaign_slug,
            entry_slug,
        ) or entry
        return jsonify(
            {
                "ok": True,
                "entry": serialize_custom_systems_entry(campaign_slug, refreshed),
                "systems": build_dm_content_systems_payload(campaign_slug),
            }
        )

    @api.post("/campaigns/<campaign_slug>/systems/custom-entries/<entry_slug>/restore")
    @api_campaign_systems_management_required
    @api_login_required
    def systems_custom_entry_restore(campaign_slug: str, entry_slug: str):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            entry = current_app.extensions["systems_service"].restore_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                actor_user_id=user.id,
            )
        except SystemsPolicyValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_restored",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "source": "api",
            },
        )
        refreshed = current_app.extensions["systems_service"].get_custom_campaign_entry_by_slug(
            campaign_slug,
            entry_slug,
        ) or entry
        return jsonify(
            {
                "ok": True,
                "entry": serialize_custom_systems_entry(campaign_slug, refreshed),
                "systems": build_dm_content_systems_payload(campaign_slug),
            }
        )

    @api.get("/campaigns/<campaign_slug>/combat")
    @api_campaign_scope_access_required("combat")
    def combat_state(campaign_slug: str):
        payload = build_combat_payload(campaign_slug)
        if should_short_circuit_live_response(
            live_revision=int(payload["live_revision"] or 0),
            live_view_token=str(payload["live_view_token"] or ""),
        ):
            return jsonify(
                {
                    "ok": True,
                    "changed": False,
                    "live_revision": payload["live_revision"],
                    "live_view_token": payload["live_view_token"],
                }
            )
        return jsonify({"ok": True, **payload})

    @api.get("/campaigns/<campaign_slug>/combat/live-state")
    @api_campaign_scope_access_required("combat")
    def combat_live_state(campaign_slug: str):
        payload = build_combat_payload(campaign_slug, include_sidebar_choices=False)
        if should_short_circuit_live_response(
            live_revision=int(payload["live_revision"] or 0),
            live_view_token=str(payload["live_view_token"] or ""),
        ):
            return jsonify(
                {
                    "ok": True,
                    "changed": False,
                    "live_revision": payload["live_revision"],
                    "live_view_token": payload["live_view_token"],
                }
            )
        return jsonify({"ok": True, **payload})

    @api.get("/campaigns/<campaign_slug>/combat/systems-monsters/search")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_search_systems_monsters(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")
        if not can_access_campaign_scope(campaign_slug, "systems"):
            return json_error("You do not have access to campaign systems.", 403, code="forbidden")

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "ok": True,
                    "results": [],
                    "message": "Type at least 2 letters to search the Systems monster list.",
                }
            )

        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if not supports_combat_tracker(campaign.system):
            return jsonify(
                {
                    "ok": True,
                    "results": [],
                    "message": "Combat tracker support for this campaign system is not available yet.",
                }
            )

        systems_service = current_app.extensions["systems_service"]
        results = []
        for entry in systems_service.search_monster_entries_for_campaign(
            campaign_slug,
            query=query,
            limit=30,
        ):
            seed = systems_service.build_monster_combat_seed(entry)
            results.append(
                {
                    "entry_key": entry.entry_key,
                    "title": entry.title,
                    "source_id": entry.source_id,
                    "subtitle": f"HP {seed.max_hp} - Speed {seed.speed_label or f'{seed.movement_total} ft.'}",
                    "initiative_bonus": (
                        f"+{seed.initiative_bonus}"
                        if seed.initiative_bonus > 0
                        else str(seed.initiative_bonus)
                    ),
                }
            )

        message = (
            "Showing the first 30 matching monsters."
            if len(results) == 30
            else (
                f"Found {len(results)} matching monster{'s' if len(results) != 1 else ''}."
                if results
                else "No Systems monsters matched that search."
            )
        )
        return jsonify({"ok": True, "results": results, "message": message})

    @api.post("/campaigns/<campaign_slug>/combat/player-combatants")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_add_player(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].add_player_character(
                campaign_slug,
                character_slug=str(payload.get("character_slug") or "").strip(),
                turn_value=payload.get("turn_value"),
                initiative_priority=payload.get("initiative_priority"),
                created_by_user_id=user.id,
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/npc-combatants")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_add_npc(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].add_npc_combatant(
                campaign_slug,
                display_name=str(payload.get("display_name") or "").strip(),
                turn_value=payload.get("turn_value"),
                initiative_bonus=payload.get("initiative_bonus"),
                dexterity_modifier=payload.get("dexterity_modifier"),
                initiative_priority=payload.get("initiative_priority"),
                current_hp=payload.get("current_hp"),
                max_hp=payload.get("max_hp"),
                temp_hp=payload.get("temp_hp"),
                movement_total=payload.get("movement_total"),
                created_by_user_id=user.id,
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/statblock-combatants")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_add_statblock_npc(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")
        if not can_access_campaign_scope(campaign_slug, "dm_content"):
            return json_error("You do not have access to DM Content.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            statblock_id = int(payload.get("statblock_id"))
        except (CampaignCombatValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc) if str(exc) else "Choose a valid DM Content statblock to add.", 400, code="validation_error")

        dm_content_service = current_app.extensions["campaign_dm_content_service"]
        statblock = dm_content_service.get_statblock(campaign_slug, statblock_id)
        if statblock is None:
            return json_error("Choose a valid DM Content statblock to add.", 400, code="validation_error")

        try:
            current_app.extensions["campaign_combat_service"].add_npc_combatant(
                campaign_slug,
                display_name=str(payload.get("display_name") or "").strip() or statblock.title,
                turn_value=payload.get("turn_value") if payload.get("turn_value") not in (None, "") else statblock.initiative_bonus,
                initiative_bonus=statblock.initiative_bonus,
                dexterity_modifier=dm_content_service.get_statblock_dexterity_modifier(statblock),
                initiative_priority=payload.get("initiative_priority"),
                current_hp=statblock.max_hp,
                max_hp=statblock.max_hp,
                temp_hp=0,
                movement_total=statblock.movement_total,
                source_kind="dm_statblock",
                source_ref=str(statblock.id),
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/systems-monsters")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_add_systems_monster(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")
        if not can_access_campaign_scope(campaign_slug, "systems"):
            return json_error("You do not have access to campaign systems.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
        except (CampaignCombatValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        entry_key = str(payload.get("entry_key") or "").strip()
        monster_entry = current_app.extensions["systems_service"].get_entry_for_campaign(campaign_slug, entry_key)
        if monster_entry is None or monster_entry.entry_type != "monster":
            return json_error("Choose a valid Systems monster to add.", 400, code="validation_error")

        monster_seed = current_app.extensions["systems_service"].build_monster_combat_seed(monster_entry)
        try:
            current_app.extensions["campaign_combat_service"].add_npc_combatant(
                campaign_slug,
                display_name=str(payload.get("display_name") or "").strip() or monster_entry.title,
                turn_value=payload.get("turn_value") if payload.get("turn_value") not in (None, "") else monster_seed.initiative_bonus,
                initiative_bonus=monster_seed.initiative_bonus,
                dexterity_modifier=monster_seed.dexterity_modifier,
                initiative_priority=payload.get("initiative_priority"),
                current_hp=monster_seed.max_hp,
                max_hp=monster_seed.max_hp,
                temp_hp=0,
                movement_total=monster_seed.movement_total,
                source_kind="systems_monster",
                source_ref=monster_entry.entry_key,
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/advance-turn")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_advance_turn(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].advance_turn(
                campaign_slug,
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/clear")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_clear(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].clear_tracker(
                campaign_slug,
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/set-current")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_set_current(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].set_current_turn(
                campaign_slug,
                combatant_id,
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.patch("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/turn")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_turn_update(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            expected_combatant_revision = payload.get("expected_combatant_revision")
            current_app.extensions["campaign_combat_service"].update_turn_value(
                campaign_slug,
                combatant_id,
                expected_revision=(
                    int(expected_combatant_revision)
                    if expected_combatant_revision is not None and str(expected_combatant_revision).strip()
                    else None
                ),
                turn_value=payload.get("turn_value"),
                initiative_priority=payload.get("initiative_priority"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            return json_error(
                "This combatant changed in another combat view. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.patch("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/vitals")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_vitals_update(campaign_slug: str, combatant_id: int):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        combat_service = current_app.extensions["campaign_combat_service"]
        combatant = combat_service.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            abort(404)

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            if combatant.is_player_character and combatant.character_slug:
                if not can_manage_campaign_combat(campaign_slug) and combatant.character_slug not in get_owned_character_slugs(campaign_slug):
                    return json_error("You do not have permission to edit this combatant.", 403, code="forbidden")
                combat_service.update_player_character_vitals(
                    campaign_slug,
                    combatant_id,
                    expected_revision=int(payload.get("expected_revision")),
                    current_hp=payload.get("current_hp"),
                    temp_hp=payload.get("temp_hp"),
                    updated_by_user_id=user.id,
                )
            else:
                if not can_manage_campaign_combat(campaign_slug):
                    return json_error("You do not have permission to edit this combatant.", 403, code="forbidden")
                expected_combatant_revision = payload.get("expected_combatant_revision")
                combat_service.update_npc_vitals(
                    campaign_slug,
                    combatant_id,
                    expected_revision=(
                        int(expected_combatant_revision)
                        if expected_combatant_revision is not None and str(expected_combatant_revision).strip()
                        else None
                    ),
                    current_hp=payload.get("current_hp"),
                    max_hp=payload.get("max_hp"),
                    temp_hp=payload.get("temp_hp"),
                    movement_total=payload.get("movement_total"),
                    updated_by_user_id=user.id,
                )
        except CharacterStateConflictError:
            return json_error(
                "This sheet changed in another session. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except CampaignCombatRevisionConflictError:
            return json_error(
                "This combatant changed in another combat view. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CampaignCombatValidationError, CharacterStateValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.patch("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/resources")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_resources_update(campaign_slug: str, combatant_id: int):
        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        combat_service = current_app.extensions["campaign_combat_service"]
        combatant = combat_service.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            abort(404)
        if combatant.is_player_character and combatant.character_slug:
            if not can_manage_campaign_combat(campaign_slug) and combatant.character_slug not in get_owned_character_slugs(
                campaign_slug
            ):
                return json_error("You do not have permission to edit this combatant.", 403, code="forbidden")
        elif not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            expected_combatant_revision = payload.get("expected_combatant_revision")
            combat_service.update_resources(
                campaign_slug,
                combatant_id,
                expected_revision=(
                    int(expected_combatant_revision)
                    if expected_combatant_revision is not None and str(expected_combatant_revision).strip()
                    else None
                ),
                has_action=coerce_bool(payload["has_action"], label="has_action") if "has_action" in payload else combatant.has_action,
                has_bonus_action=coerce_bool(payload["has_bonus_action"], label="has_bonus_action") if "has_bonus_action" in payload else combatant.has_bonus_action,
                has_reaction=coerce_bool(payload["has_reaction"], label="has_reaction") if "has_reaction" in payload else combatant.has_reaction,
                movement_remaining=payload.get("movement_remaining", combatant.movement_remaining),
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            return json_error(
                "This combatant changed in another combat view. Refresh and try again.",
                409,
                code="state_conflict",
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_condition_create(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].add_condition(
                campaign_slug,
                combatant_id,
                name=str(payload.get("name") or "").strip(),
                duration_text=str(payload.get("duration_text") or "").strip(),
                created_by_user_id=user.id,
            )
        except (CampaignCombatValidationError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.delete("/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_condition_delete(campaign_slug: str, condition_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        try:
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].delete_condition(campaign_slug, condition_id)
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.delete("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>")
    @api_campaign_scope_access_required("combat")
    @api_login_required
    def combat_combatant_delete(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            return json_error("You do not have permission to manage combat.", 403, code="forbidden")

        try:
            require_supported_combat_campaign(campaign_slug)
            current_app.extensions["campaign_combat_service"].delete_combatant(campaign_slug, combatant_id)
        except CampaignCombatValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.get("/campaigns/<campaign_slug>/characters")
    def character_list(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        can_access_character_roster = can_access_campaign_scope(campaign_slug, "characters")
        owned_character_slugs = get_owned_character_slugs(campaign_slug)
        if not can_access_character_roster and not owned_character_slugs:
            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have access to campaign characters.", 403, code="forbidden")

        records = get_character_repository().list_visible_characters(campaign_slug)
        if not can_access_character_roster:
            records = [
                record
                for record in records
                if record.definition.character_slug in owned_character_slugs
            ]
        query = request.args.get("q", "").strip()
        character_cards = [serialize_character_summary(campaign, record) for record in records]
        if query:
            normalized_query = query.lower()
            character_cards = [
                card for card in character_cards if normalized_query in str(card.get("search_text") or "")
            ]
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "characters": character_cards,
                "query": query,
                "result_count": len(character_cards),
                "tools": serialize_character_roster_tools(campaign_slug, campaign),
                "links": serialize_character_roster_links(campaign_slug, campaign),
            }
        )

    @api.get("/campaigns/<campaign_slug>/characters/create")
    def character_create_context(campaign_slug: str):
        campaign, access_error = ensure_character_authoring_access(campaign_slug)
        if access_error is not None:
            return access_error
        return jsonify(build_character_create_payload(campaign_slug, campaign, dict(request.args)))

    @api.post("/campaigns/<campaign_slug>/characters/create")
    def character_create_submit(campaign_slug: str):
        campaign, access_error = ensure_character_authoring_access(campaign_slug)
        if access_error is not None:
            return access_error

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")
        values = normalize_character_authoring_values(payload)
        lane = native_character_create_lane(getattr(campaign, "system", ""))
        try:
            if lane == CHARACTER_ROUTE_LANE_XIANXIA:
                create_context = build_xianxia_character_create_context(
                    values,
                    systems_service=current_app.extensions["systems_service"],
                    campaign_slug=campaign_slug,
                )
                definition, import_metadata = build_xianxia_character_definition(
                    campaign_slug,
                    create_context,
                    values,
                )
                initial_state = build_xianxia_character_initial_state(definition, values)
            elif lane == CHARACTER_ROUTE_LANE_DND5E:
                builder_context = build_level_one_builder_context(
                    current_app.extensions["systems_service"],
                    campaign_slug,
                    values,
                    campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
                )
                builder_ready = bool(
                    builder_context.get("class_options")
                    and builder_context.get("species_options")
                    and builder_context.get("background_options")
                )
                if not builder_ready:
                    return json_error(
                        "The native character builder needs a supported base class plus enabled Systems species and backgrounds first.",
                        400,
                        code="validation_error",
                    )
                definition, import_metadata = build_level_one_character_definition(
                    campaign_slug,
                    builder_context,
                    values,
                )
                definition = finalize_character_definition_for_write(campaign_slug, definition)
                initial_state = build_initial_state(definition)
            else:
                return json_error(
                    native_character_create_unsupported_message(getattr(campaign, "system", "")),
                    400,
                    code="unsupported_campaign_system",
                )
            record = write_new_character_record(campaign_slug, definition, import_metadata, initial_state)
        except CharacterBuildError as exc:
            return json_error(str(exc), 400, code="validation_error")
        except FileExistsError as exc:
            return json_error(str(exc), 409, code="character_exists")
        except (CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "message": f"{record.definition.name} created.",
                "character": serialize_character_record(campaign_slug, record),
                "links": {
                    **serialize_character_authoring_links(campaign_slug, campaign),
                    "character_url": (
                        f"/app-next/campaigns/{campaign_slug}/characters/"
                        f"{record.definition.character_slug}"
                    ),
                    "flask_character_url": url_for(
                        "character_read_view",
                        campaign_slug=campaign_slug,
                        character_slug=record.definition.character_slug,
                    ),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/characters/import/xianxia-manual")
    def character_xianxia_manual_import_context(campaign_slug: str):
        campaign, access_error = ensure_character_authoring_access(campaign_slug)
        if access_error is not None:
            return access_error
        if native_character_create_lane(getattr(campaign, "system", "")) != CHARACTER_ROUTE_LANE_XIANXIA:
            return json_error(
                "Manual Xianxia character import is only available for Xianxia campaigns.",
                400,
                code="unsupported_campaign_system",
            )
        values = normalize_character_authoring_values({"values": dict(request.args)})
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "lane": CHARACTER_ROUTE_LANE_XIANXIA,
                "links": serialize_character_authoring_links(campaign_slug, campaign),
                "import_context": build_xianxia_manual_import_context(campaign_slug, values),
            }
        )

    @api.post("/campaigns/<campaign_slug>/characters/import/xianxia-manual")
    def character_xianxia_manual_import_submit(campaign_slug: str):
        campaign, access_error = ensure_character_authoring_access(campaign_slug)
        if access_error is not None:
            return access_error
        if native_character_create_lane(getattr(campaign, "system", "")) != CHARACTER_ROUTE_LANE_XIANXIA:
            return json_error(
                "Manual Xianxia character import is only available for Xianxia campaigns.",
                400,
                code="unsupported_campaign_system",
            )
        try:
            request_payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        values = normalize_character_authoring_values(request_payload)
        import_context = build_xianxia_manual_import_context(campaign_slug, values)
        import_payload = build_xianxia_manual_import_payload(values)
        try:
            definition, import_metadata, initial_state = build_xianxia_manual_import_character(
                import_payload,
                campaign_slug=campaign_slug,
                martial_art_options=list(import_context.get("martial_art_options") or []),
            )
            preview = build_xianxia_manual_import_preview(definition, initial_state)
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        if not bool(request_payload.get("confirm_import")):
            return jsonify(
                {
                    "ok": True,
                    "message": "Review the imported sheet summary, then confirm to create the character.",
                    "campaign": serialize_campaign(campaign),
                    "lane": CHARACTER_ROUTE_LANE_XIANXIA,
                    "links": serialize_character_authoring_links(campaign_slug, campaign),
                    "import_context": build_xianxia_manual_import_context(
                        campaign_slug,
                        values,
                        preview=preview,
                    ),
                }
            )

        try:
            record = write_new_character_record(campaign_slug, definition, import_metadata, initial_state)
        except FileExistsError as exc:
            return json_error(str(exc), 409, code="character_exists")

        return jsonify(
            {
                "ok": True,
                "message": f"{record.definition.name} imported.",
                "character": serialize_character_record(campaign_slug, record),
                "links": {
                    **serialize_character_authoring_links(campaign_slug, campaign),
                    "character_url": (
                        f"/app-next/campaigns/{campaign_slug}/characters/"
                        f"{record.definition.character_slug}"
                    ),
                    "flask_character_url": url_for(
                        "character_read_view",
                        campaign_slug=campaign_slug,
                        character_slug=record.definition.character_slug,
                    ),
                },
            }
        )

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>")
    def character_detail(campaign_slug: str, character_slug: str):
        if not can_access_campaign_scope(campaign_slug, "characters") and not has_session_mode_access(
            campaign_slug,
            character_slug,
        ):
            if get_current_user() is None:
                return json_error("Authentication required.", 401, code="auth_required")
            return json_error("You do not have access to this character.", 403, code="forbidden")
        record = load_character_record(campaign_slug, character_slug)
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        return jsonify(
            {
                "ok": True,
                "character": serialize_character_record(campaign_slug, record),
                "links": serialize_character_links(campaign_slug, campaign, record),
            }
        )

    def load_character_controls_target(campaign_slug: str, character_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if not supports_character_controls_routes(getattr(campaign, "system", "")):
            abort(404)
        record = load_character_record(campaign_slug, character_slug)
        return campaign, record

    def serialize_character_controls_response(
        campaign_slug: str,
        campaign,
        record: CharacterRecord,
        *,
        message: str,
    ):
        return jsonify(
            {
                "ok": True,
                "message": message,
                "character": serialize_character_record(campaign_slug, record),
                "links": serialize_character_links(campaign_slug, campaign, record),
            }
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment")
    @api_login_required
    def character_controls_assignment_update(campaign_slug: str, character_slug: str):
        campaign, record = load_character_controls_target(campaign_slug, character_slug)
        actor = get_current_user()
        if actor is None:
            return json_error("Authentication required.", 401, code="auth_required")
        if not actor.is_admin:
            return json_error("You do not have permission to assign character owners.", 403, code="forbidden")

        try:
            payload = load_json_object()
            target_user_id = int(payload.get("user_id"))
        except (TypeError, ValueError):
            return json_error("Choose a valid player to assign.", 400, code="validation_error")

        store = get_auth_store()
        target_user = store.get_user_by_id(target_user_id)
        if target_user is None or not target_user.is_active:
            return json_error("Choose an active player account to assign.", 400, code="validation_error")

        membership = store.get_membership(target_user.id, campaign_slug, statuses=("active",))
        if membership is None or membership.role != "player":
            return json_error(
                "Character owners must have an active player membership in that campaign.",
                400,
                code="validation_error",
            )

        previous = store.get_character_assignment(campaign_slug, character_slug)
        assignment = store.upsert_character_assignment(target_user.id, campaign_slug, character_slug)
        store.write_audit_event(
            event_type="character_assignment_created",
            actor_user_id=actor.id,
            target_user_id=target_user.id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "previous_user_id": previous.user_id if previous is not None else None,
                "assignment_type": assignment.assignment_type,
                "source": "gen2_character_controls",
            },
        )

        return serialize_character_controls_response(
            campaign_slug,
            campaign,
            record,
            message=f"Assigned {character_slug} to {target_user.email}.",
        )

    @api.delete("/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment")
    @api_login_required
    def character_controls_assignment_delete(campaign_slug: str, character_slug: str):
        campaign, record = load_character_controls_target(campaign_slug, character_slug)
        actor = get_current_user()
        if actor is None:
            return json_error("Authentication required.", 401, code="auth_required")
        if not actor.is_admin:
            return json_error("You do not have permission to assign character owners.", 403, code="forbidden")

        store = get_auth_store()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        if assignment is None:
            return json_error(
                "That character does not currently have an assigned player.",
                400,
                code="validation_error",
            )

        removed_assignment = store.delete_character_assignment(campaign_slug, character_slug)
        if removed_assignment is None:
            return json_error("That character assignment no longer exists.", 400, code="validation_error")

        store.write_audit_event(
            event_type="character_assignment_removed",
            actor_user_id=actor.id,
            target_user_id=removed_assignment.user_id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "assignment_type": removed_assignment.assignment_type,
                "source": "gen2_character_controls",
            },
        )

        return serialize_character_controls_response(
            campaign_slug,
            campaign,
            record,
            message=f"Cleared assignment for {character_slug}.",
        )

    @api.delete("/campaigns/<campaign_slug>/characters/<character_slug>/controls")
    @api_login_required
    def character_controls_delete(campaign_slug: str, character_slug: str):
        campaign, record = load_character_controls_target(campaign_slug, character_slug)
        if not can_manage_campaign_content(campaign_slug):
            return json_error("You do not have permission to delete this character.", 403, code="forbidden")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")
        confirmation = str(payload.get("confirm_character_slug") or "").strip()
        if confirmation != character_slug:
            return json_error(f"Type {character_slug} to confirm deletion.", 400, code="validation_error")

        store = get_auth_store()
        actor = get_current_user()
        previous_assignment = store.get_character_assignment(campaign_slug, character_slug)
        deleted = delete_campaign_character_file(
            current_app.config["CAMPAIGNS_DIR"],
            campaign_slug,
            character_slug,
            state_store=current_app.extensions["character_state_store"],
            auth_store=store,
        )
        if deleted is None:
            return json_error("That character no longer exists.", 404, code="not_found")

        store.write_audit_event(
            event_type="character_deleted",
            actor_user_id=actor.id if actor is not None else None,
            target_user_id=previous_assignment.user_id if previous_assignment is not None else None,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "deleted_files": deleted.deleted_files,
                "deleted_state": deleted.deleted_state,
                "deleted_assignment": deleted.deleted_assignment,
                "deleted_assets": deleted.deleted_assets,
                "source": "gen2_character_controls",
            },
        )
        return jsonify(
            {
                "ok": True,
                "message": f"Deleted character {record.definition.name}.",
                "deleted_character_slug": character_slug,
                "deleted_character_name": record.definition.name,
                "links": {
                    "gen2_roster_url": gen2_campaign_href(campaign_slug, "characters"),
                    "flask_roster_url": url_for("character_roster_view", campaign_slug=campaign.slug),
                },
            }
        )

    @api.put("/campaigns/<campaign_slug>/characters/<character_slug>/portrait")
    def character_portrait_upsert(campaign_slug: str, character_slug: str):
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return json_error("You do not have permission to update this character from this view.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            portrait_payload = validate_character_portrait_payload(payload)
            existing_asset_ref = str((record.definition.profile or {}).get("portrait_asset_ref") or "").strip()
            next_asset_ref = build_character_portrait_asset_ref(character_slug, portrait_payload["filename"])
            definition = update_character_portrait_profile(
                record.definition,
                asset_ref=next_asset_ref,
                alt_text=portrait_payload["alt_text"],
                caption=portrait_payload["caption"],
            )
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = merge_state_with_definition(definition, record.state_record.state)
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
            write_campaign_asset_file(campaign, next_asset_ref, data_blob=portrait_payload["data_blob"])
            if existing_asset_ref and existing_asset_ref != next_asset_ref:
                delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            return json_error("This sheet changed in another session. Refresh and try again.", 409, code="state_conflict")
        except (CampaignContentError, CharacterEditValidationError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return serialize_updated_character(campaign_slug, character_slug)

    @api.delete("/campaigns/<campaign_slug>/characters/<character_slug>/portrait")
    def character_portrait_delete(campaign_slug: str, character_slug: str):
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return json_error("You do not have permission to update this character from this view.", 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        existing_asset_ref = str((record.definition.profile or {}).get("portrait_asset_ref") or "").strip()
        if not existing_asset_ref:
            return json_error("That character does not currently have a portrait.", 400, code="validation_error")

        try:
            payload = load_json_object()
            expected_revision = int(payload.get("expected_revision"))
            definition = update_character_portrait_profile(record.definition)
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = merge_state_with_definition(definition, record.state_record.state)
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
            delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            return json_error("This sheet changed in another session. Refresh and try again.", 409, code="state_conflict")
        except (CampaignContentError, CharacterEditValidationError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return serialize_updated_character(campaign_slug, character_slug)

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>")
    @api_login_required
    def character_rest_preview(campaign_slug: str, character_slug: str, rest_type: str):
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return json_error("You do not have permission to use rest actions for this character.", 403, code="forbidden")

        try:
            preview = get_character_state_service().preview_rest(record, rest_type)
        except ValueError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
                "preview": {
                    "rest_type": preview.rest_type,
                    "label": preview.label,
                    "changes": [
                        {
                            "label": change.label,
                            "from_value": change.from_value,
                            "to_value": change.to_value,
                        }
                        for change in preview.changes
                    ],
                },
            }
        )

    def run_character_mutation(
        campaign_slug: str,
        character_slug: str,
        action,
        *,
        forbidden_message: str = "You do not have permission to update this character from this view.",
        conflict_message: str = "This sheet changed in another session. Refresh and try again.",
    ):
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return json_error(forbidden_message, 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        try:
            action(record, payload, user.id)
        except CharacterStateConflictError:
            return json_error(conflict_message, 409, code="state_conflict")
        except (CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return serialize_updated_character(campaign_slug, character_slug)

    def finalize_character_definition_for_write(campaign_slug: str, definition):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)
        if not supports_native_character_tools(getattr(campaign, "system", "")):
            return definition
        return normalize_definition_to_native_model(
            definition,
            item_catalog=build_character_item_catalog(campaign_slug),
            systems_service=current_app.extensions["systems_service"],
        )

    def run_character_definition_mutation(
        campaign_slug: str,
        character_slug: str,
        action,
        *,
        forbidden_message: str = "You do not have permission to update this character from this view.",
        conflict_message: str = "This sheet changed in another session. Refresh and try again.",
    ):
        record = load_character_record(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            return json_error(forbidden_message, 403, code="forbidden")

        user = get_current_user()
        if user is None:
            return json_error("Authentication required.", 401, code="auth_required")

        try:
            payload = load_json_object()
        except ValueError as exc:
            return json_error(str(exc), 400, code="invalid_json")

        try:
            expected_revision = int(payload.get("expected_revision"))
            result = action(record, payload, user.id)
            inventory_state_overrides = None
            if isinstance(result, tuple) and len(result) == 4:
                definition, import_metadata, inventory_quantity_overrides, inventory_state_overrides = result
            else:
                definition, import_metadata, inventory_quantity_overrides = result
            definition = finalize_character_definition_for_write(campaign_slug, definition)
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                inventory_quantity_overrides=inventory_quantity_overrides,
                inventory_state_overrides=inventory_state_overrides,
            )
            current_app.extensions["character_state_store"].replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(current_app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            return json_error(conflict_message, 409, code="state_conflict")
        except (CharacterEditValidationError, CharacterStateValidationError, TypeError, ValueError) as exc:
            return json_error(str(exc), 400, code="validation_error")

        return serialize_updated_character(campaign_slug, character_slug)

    def build_equipment_state_update_result(
        campaign_slug: str,
        record: CharacterRecord,
        item_id: str,
        payload: dict[str, Any],
        *,
        item_catalog: dict[str, object],
    ):
        inventory_by_ref = {
            build_character_inventory_item_ref(item): dict(item)
            for item in list((record.state_record.state or {}).get("inventory") or [])
            if build_character_inventory_item_ref(item)
        }
        if item_id not in inventory_by_ref:
            raise CharacterEditValidationError("Choose a valid equipment entry to update.")
        _, support_lookup = build_record_equipment_support_lookup(
            record,
            item_catalog=item_catalog,
        )
        target_support = dict(support_lookup.get(item_id) or {})
        if not bool(target_support.get("supports_equipped_state")):
            raise CharacterEditValidationError(
                "That inventory row stays on Inventory because it does not support equipment state."
            )

        weapon_wield_mode = ""
        if bool(target_support.get("supports_weapon_wield_mode")):
            weapon_wield_mode = _normalize_weapon_wield_mode_value(payload.get("weapon_wield_mode"))
            allowed_modes = [
                _normalize_weapon_wield_mode_value(value)
                for value in list(target_support.get("weapon_wield_modes") or [])
                if _normalize_weapon_wield_mode_value(value)
            ]
            allowed_mode_set = set(allowed_modes)
            if weapon_wield_mode and weapon_wield_mode not in allowed_mode_set:
                raise CharacterEditValidationError("Choose a valid wielding mode for that weapon.")
            if not weapon_wield_mode and bool(payload.get("is_equipped")) and allowed_modes:
                weapon_wield_mode = allowed_modes[0]
            is_equipped = bool(weapon_wield_mode)
        else:
            is_equipped = bool(payload.get("is_equipped"))

        requested_attunement = bool(payload.get("is_attuned"))
        if requested_attunement and not bool(target_support.get("supports_attunement")):
            raise CharacterEditValidationError(
                "Only items whose durable metadata explicitly requires attunement can be attuned."
            )
        is_attuned = bool(requested_attunement and target_support.get("supports_attunement"))
        attunement_payload = dict((record.state_record.state or {}).get("attunement") or {})
        max_attuned_items = int(attunement_payload.get("max_attuned_items") or 3)
        currently_attuned_refs = {
            item_ref
            for item_ref, item in inventory_by_ref.items()
            if (
                item_ref != item_id
                and bool(item.get("is_attuned", False))
                and bool(dict(support_lookup.get(item_ref) or {}).get("supports_attunement"))
            )
        }
        next_attuned_count = len(currently_attuned_refs) + (1 if is_attuned else 0)
        if max_attuned_items >= 0 and next_attuned_count > max_attuned_items:
            raise CharacterEditValidationError(
                f"This character already has {max_attuned_items} attuned item"
                f"{'' if max_attuned_items == 1 else 's'}. Clear one first."
            )

        definition, import_metadata = apply_equipment_state_edit(
            campaign_slug,
            record.definition,
            record.import_metadata,
            item_catalog=item_catalog,
            systems_service=current_app.extensions["systems_service"],
            target_item_id=item_id,
            is_equipped=is_equipped,
            is_attuned=is_attuned,
            weapon_wield_mode=weapon_wield_mode,
        )
        return (
            definition,
            import_metadata,
            {},
            {
                item_id: {
                    "is_equipped": is_equipped,
                    "is_attuned": is_attuned,
                    "weapon_wield_mode": weapon_wield_mode,
                }
            },
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/sheet-edit")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_sheet_edit_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().save_character_sheet_edit(
                record,
                expected_revision=int(payload.get("expected_revision")),
                vitals=payload.get("vitals"),
                resources=payload.get("resources"),
                spell_slots=payload.get("spell_slots"),
                inventory=payload.get("inventory"),
                currency=payload.get("currency"),
                notes=payload.get("notes"),
                personal=payload.get("personal"),
                updated_by_user_id=user_id,
            ),
            forbidden_message="You do not have permission to edit Character page state for this character.",
            conflict_message=(
                "This sheet changed before your batch save finished. Refresh and review the latest sheet before "
                "saving again. Session Character, Combat, or another tab may have changed nearby fields first; "
                "nothing was auto-merged."
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals")
    @api_login_required
    def character_vitals_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_vitals(
                record,
                expected_revision=int(payload.get("expected_revision")),
                current_hp=payload.get("current_hp"),
                temp_hp=payload.get("temp_hp"),
                current_stance=payload.get("current_stance"),
                temp_stance=payload.get("temp_stance"),
                current_jing=payload.get("current_jing"),
                current_qi=payload.get("current_qi"),
                current_shen=payload.get("current_shen"),
                current_yin=payload.get("current_yin"),
                current_yang=payload.get("current_yang"),
                current_dao=payload.get("current_dao"),
                hp_delta=payload.get("hp_delta"),
                temp_hp_delta=payload.get("temp_hp_delta"),
                clear_temp_hp=bool(payload.get("clear_temp_hp")),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>")
    @api_login_required
    def character_resource_update(campaign_slug: str, character_slug: str, resource_id: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_resource(
                record,
                resource_id,
                expected_revision=int(payload.get("expected_revision")),
                current=payload.get("current"),
                delta=payload.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level>")
    @api_login_required
    def character_spell_slots_update(campaign_slug: str, character_slug: str, level: int):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_spell_slots(
                record,
                level,
                slot_lane_id=str(payload.get("slot_lane_id") or ""),
                expected_revision=int(payload.get("expected_revision")),
                used=payload.get("used"),
                delta_used=payload.get("delta_used"),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>")
    @api_login_required
    def character_inventory_update(campaign_slug: str, character_slug: str, item_id: str):
        def update_inventory(record, payload, user_id):
            if is_xianxia_system(record.definition.system):
                return get_character_state_service().update_xianxia_inventory_quantity(
                    record,
                    item_id,
                    expected_revision=int(payload.get("expected_revision")),
                    quantity=payload.get("quantity"),
                    delta=payload.get("delta"),
                    updated_by_user_id=user_id,
                )
            return get_character_state_service().update_inventory_quantity(
                record,
                item_id,
                expected_revision=int(payload.get("expected_revision")),
                quantity=payload.get("quantity"),
                delta=payload.get("delta"),
                updated_by_user_id=user_id,
            )

        return run_character_mutation(
            campaign_slug,
            character_slug,
            update_inventory,
        )

    def xianxia_inventory_item_payload(payload: dict[str, Any]) -> dict[str, Any]:
        item = payload.get("item")
        if isinstance(item, dict):
            source = item
        else:
            source = payload
        item_payload: dict[str, Any] = {
            "id": str(source.get("id") or source.get("item_id") or "").strip(),
            "name": str(source.get("name") or "").strip(),
            "quantity": source.get("quantity", 1),
            "item_nature": str(source.get("item_nature") or "").strip(),
            "item_type": str(source.get("item_type") or "").strip(),
            "notes": str(source.get("notes") or "").strip(),
            "tags": source.get("tags", []),
            "catalog_ref": str(source.get("catalog_ref") or "").strip(),
            "systems_ref": source.get("systems_ref"),
            "equippable": source.get("equippable"),
            "is_equipped": source.get("is_equipped"),
        }
        return {key: value for key, value in item_payload.items() if value not in ("", None)}

    def json_payload_value(payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload:
                return payload.get(key)
        return None

    def optional_json_int(payload: dict[str, Any], *keys: str, field_label: str) -> int | None:
        raw_value = json_payload_value(payload, *keys)
        if raw_value is None or str(raw_value).strip() == "":
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_label} must be an integer.") from exc
        if value < 0:
            raise ValueError(f"{field_label} must be 0 or greater.")
        return value

    def required_json_int(payload: dict[str, Any], *keys: str, field_label: str) -> int:
        value = optional_json_int(payload, *keys, field_label=field_label)
        if value is None:
            raise ValueError(f"{field_label} is required.")
        return value

    def ensure_xianxia_character_definition(record: CharacterRecord, message: str) -> None:
        if not is_xianxia_system(getattr(record.definition, "system", "")):
            raise ValueError(message)

    def managed_character_import_metadata(campaign_slug: str, record: CharacterRecord):
        return build_managed_character_import_metadata(
            campaign_slug,
            record.definition.character_slug,
            record.import_metadata,
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state")
    @api_login_required
    def character_xianxia_active_state_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_xianxia_active_state(
                record,
                expected_revision=int(payload.get("expected_revision")),
                active_stance_name=payload.get("active_stance_name"),
                active_aura_name=payload.get("active_aura_name"),
                updated_by_user_id=user_id,
            ),
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-requests")
    @api_login_required
    def character_xianxia_dao_immolating_use_request(campaign_slug: str, character_slug: str):
        def request_dao_use(record: CharacterRecord, payload: dict[str, Any], user_id: int):
            ensure_xianxia_character_definition(
                record,
                "Dao Immolating use requests are only available for Xianxia character sheets.",
            )
            request_result = request_xianxia_dao_immolating_use_definition(
                record.definition,
                request_name=str(
                    json_payload_value(payload, "request_name", "dao_immolating_request_name") or ""
                ),
                notes=str(json_payload_value(payload, "notes", "dao_immolating_request_notes") or ""),
                prepared_record_index=optional_json_int(
                    payload,
                    "prepared_record_index",
                    "dao_immolating_prepared_index",
                    field_label="Prepared Dao Immolating Technique note",
                ),
            )
            return request_result.definition, managed_character_import_metadata(campaign_slug, record), {}

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            request_dao_use,
            forbidden_message="You do not have permission to request Dao Immolating use for this character.",
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-dao-immolating-use-records")
    @api_login_required
    def character_xianxia_dao_immolating_use_record(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            return json_error(
                "You do not have permission to record Dao Immolating use for this character.",
                403,
                code="forbidden",
            )

        def record_dao_use(record: CharacterRecord, payload: dict[str, Any], user_id: int):
            ensure_xianxia_character_definition(
                record,
                "Dao Immolating use records are only available for Xianxia character sheets.",
            )
            use_result = record_xianxia_dao_immolating_use_definition(
                record.definition,
                use_record_index=required_json_int(
                    payload,
                    "use_record_index",
                    "dao_immolating_use_index",
                    field_label="Dao Immolating Technique use",
                ),
                notes=str(json_payload_value(payload, "notes", "dao_immolating_use_notes") or ""),
            )
            return use_result.definition, managed_character_import_metadata(campaign_slug, record), {}

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            record_dao_use,
            forbidden_message="You do not have permission to record Dao Immolating use for this character.",
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory")
    @api_login_required
    def character_xianxia_inventory_add(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().add_xianxia_inventory_item(
                record,
                xianxia_inventory_item_payload(payload),
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>")
    @api_login_required
    def character_xianxia_inventory_item_update(campaign_slug: str, character_slug: str, item_id: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_xianxia_inventory_item(
                record,
                item_id,
                xianxia_inventory_item_payload(payload),
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    @api.delete("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>")
    @api_login_required
    def character_xianxia_inventory_item_remove(campaign_slug: str, character_slug: str, item_id: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().remove_xianxia_inventory_item(
                record,
                item_id,
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped")
    @api_login_required
    def character_xianxia_inventory_equipped_update(campaign_slug: str, character_slug: str, item_id: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_xianxia_inventory_equipped_state(
                record,
                item_id,
                expected_revision=int(payload.get("expected_revision")),
                is_equipped=bool(payload.get("is_equipped")),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/equipment/<item_id>")
    @api_login_required
    def character_equipment_state_update(campaign_slug: str, character_slug: str, item_id: str):
        item_catalog = build_character_item_catalog(campaign_slug)
        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: build_equipment_state_update_result(
                campaign_slug,
                record,
                item_id,
                payload,
                item_catalog=item_catalog,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/feature-states/<feature_key>")
    @api_login_required
    def character_feature_state_update(campaign_slug: str, character_slug: str, feature_key: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_feature_state(
                record,
                feature_key,
                expected_revision=int(payload.get("expected_revision")),
                enabled=bool(payload.get("enabled")),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/currency")
    @api_login_required
    def character_currency_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_currency(
                record,
                expected_revision=int(payload.get("expected_revision")),
                values={
                    key: payload.get(key)
                    for key in (
                        "cp",
                        "sp",
                        "ep",
                        "gp",
                        "pp",
                        "coin",
                        "supply",
                        "spirit_stones",
                    )
                },
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/notes")
    @api_login_required
    def character_notes_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_player_notes(
                record,
                expected_revision=int(payload.get("expected_revision")),
                notes_markdown=str(payload.get("player_notes_markdown") or ""),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/personal")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_personal_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_personal_details(
                record,
                expected_revision=int(payload.get("expected_revision")),
                physical_description_markdown=str(payload.get("physical_description_markdown") or ""),
                background_markdown=str(payload.get("background_markdown") or ""),
                updated_by_user_id=user_id,
            ),
        )

    @api.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>")
    @api_login_required
    def character_rest_apply(campaign_slug: str, character_slug: str, rest_type: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().apply_rest(
                record,
                rest_type,
                expected_revision=int(payload.get("expected_revision")),
                updated_by_user_id=user_id,
            ),
        )

    app.register_blueprint(api)
