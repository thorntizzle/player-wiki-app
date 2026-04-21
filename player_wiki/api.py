from __future__ import annotations

import base64
import binascii
import mimetypes
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request, send_file, url_for

from .auth import (
    can_access_campaign_scope,
    can_access_campaign_systems_entry,
    can_access_campaign_systems_source,
    can_manage_campaign_combat,
    can_manage_campaign_content,
    can_manage_campaign_dm_content,
    can_manage_campaign_session,
    can_manage_campaign_systems,
    can_post_campaign_session_messages,
    get_accessible_campaign_entries,
    get_auth_store,
    get_campaign_role,
    get_campaign_scope_visibility,
    get_current_auth_source,
    get_current_memberships,
    get_current_user,
    get_effective_campaign_visibility,
    get_public_campaign_entries,
    get_repository,
    has_session_mode_access,
)
from .auth_store import isoformat
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
    list_campaign_asset_files,
    list_campaign_character_files,
    list_campaign_page_files,
    update_campaign_config_file,
    write_campaign_asset_file,
    write_campaign_character_file,
    write_campaign_page_file,
)
from .campaign_dm_content_service import CampaignDMContentValidationError
from .campaign_session_service import CampaignSessionValidationError
from .campaign_visibility import CAMPAIGN_VISIBILITY_SCOPES
from .character_models import CharacterRecord, CharacterStateRecord
from .character_profile import profile_class_level_text
from .character_service import CharacterStateValidationError
from .character_store import CharacterStateConflictError
from .combat_presenter import DND_5E_CONDITION_OPTIONS, present_combat_tracker
from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
    parse_session_article_source_ref,
)
from .systems_importer import Dnd5eSystemsImporter, SUPPORTED_ENTRY_TYPES
from .systems_ingest import SystemsIngestError, extracted_systems_archive
from .systems_service import LICENSE_CLASS_LABELS, SystemsPolicyValidationError
from .version import build_app_metadata

SUPPORTED_COMBAT_SYSTEM = "DND-5E"
SYSTEMS_ENTRY_TYPE_LABELS = {
    "action": "Actions",
    "background": "Backgrounds",
    "book": "Book Chapters",
    "class": "Classes",
    "classfeature": "Class Features",
    "condition": "Conditions",
    "disease": "Diseases",
    "feat": "Feats",
    "item": "Items",
    "monster": "Monsters",
    "optionalfeature": "Optional Features",
    "race": "Races",
    "rule": "Rules",
    "sense": "Senses",
    "skill": "Skills",
    "spell": "Spells",
    "status": "Statuses",
    "subclass": "Subclasses",
    "subclassfeature": "Subclass Features",
    "variantrule": "Variant Rules",
}
SYSTEMS_ENTRY_TYPE_ORDER = (
    "book",
    "class",
    "subclass",
    "classfeature",
    "subclassfeature",
    "spell",
    "feat",
    "optionalfeature",
    "item",
    "race",
    "rule",
    "background",
    "action",
    "skill",
    "sense",
    "variantrule",
    "condition",
    "status",
    "disease",
    "monster",
)
SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES = {"classfeature", "optionalfeature", "subclassfeature"}


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
                return json_error("You do not have permission to manage shared systems imports.", 403, code="forbidden")
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

    def entry_type_label(entry_type: str) -> str:
        normalized = str(entry_type or "").strip().lower()
        return SYSTEMS_ENTRY_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title())

    def systems_entry_type_sort_key(entry_type: str) -> tuple[int, str]:
        try:
            return (SYSTEMS_ENTRY_TYPE_ORDER.index(entry_type), entry_type)
        except ValueError:
            return (len(SYSTEMS_ENTRY_TYPE_ORDER), entry_type)

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

    def serialize_session_article(campaign_slug: str, article, article_image=None) -> dict[str, Any]:
        source_kind, source_ref = parse_session_article_source_ref(article.source_page_ref)
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
    ) -> dict[str, Any]:
        article = article_lookup.get(message.article_id) if message.article_id is not None else None
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
            "article": (
                serialize_session_article(campaign_slug, article, article_images.get(article.id))
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

        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return []

        results: list[dict[str, str]] = []
        page_records = get_campaign_page_store().search_page_records(
            campaign.slug,
            normalized_query,
            limit=max(limit, 1) * 2,
            include_body=False,
        )
        for record in page_records:
            if not campaign.is_page_visible(record.page):
                continue
            context_parts = [record.page.section]
            if record.page.subsection:
                context_parts.append(record.page.subsection)
            results.append(
                {
                    "source_ref": build_session_article_page_source_ref(record.page_ref),
                    "source_kind": SESSION_ARTICLE_SOURCE_KIND_PAGE,
                    "title": record.page.title,
                    "subtitle": " / ".join(part for part in context_parts if part),
                    "kind_label": "Wiki",
                    "select_label": f"{record.page.title} - Wiki - {' / '.join(part for part in context_parts if part)}",
                }
            )
            if len(results) >= limit:
                return results

        if can_access_campaign_scope(campaign_slug, "systems"):
            systems_entries = current_app.extensions["systems_service"].search_entries_for_campaign(
                campaign_slug,
                query=normalized_query,
                limit=max(limit, 1) * 2,
            )
            for entry in systems_entries:
                if not can_access_campaign_systems_entry(campaign_slug, entry.slug):
                    continue
                results.append(
                    {
                        "source_ref": build_session_article_systems_source_ref(entry.slug),
                        "source_kind": SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
                        "title": entry.title,
                        "subtitle": f"{entry_type_label(entry.entry_type)} - {entry.source_id}",
                        "kind_label": "Systems",
                        "select_label": f"{entry.title} - Systems - {entry_type_label(entry.entry_type)} - {entry.source_id}",
                    }
                )
                if len(results) >= limit:
                    break

        return results

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

        messages = []
        if active_session is not None:
            messages = [
                serialize_session_message(
                    campaign_slug,
                    message,
                    article_lookup,
                    article_images,
                )
                for message in session_service.list_messages(active_session.id)
            ]

        payload: dict[str, Any] = {
            "campaign": serialize_campaign(campaign),
            "permissions": {
                "can_manage_session": can_manage_session,
                "can_post_messages": can_post_messages,
            },
            "active_session": serialize_session_record(active_session) if active_session is not None else None,
            "messages": messages,
        }

        if can_manage_session:
            payload["staged_articles"] = [
                serialize_session_article(campaign_slug, article, article_images.get(article.id))
                for article in article_lookup.values()
                if not article.is_revealed
            ]
            payload["revealed_articles"] = [
                serialize_session_article(campaign_slug, article, article_images.get(article.id))
                for article in article_lookup.values()
                if article.is_revealed
            ]
            payload["session_logs"] = [
                serialize_session_log_summary(summary)
                for summary in session_service.list_session_logs(campaign_slug, limit=20)
            ]

        return payload

    def serialize_dm_statblock(statblock) -> dict[str, Any]:
        return {
            "id": statblock.id,
            "campaign_slug": statblock.campaign_slug,
            "title": statblock.title,
            "body_markdown": statblock.body_markdown,
            "source_filename": statblock.source_filename,
            "armor_class": statblock.armor_class,
            "max_hp": statblock.max_hp,
            "speed_text": statblock.speed_text,
            "movement_total": statblock.movement_total,
            "initiative_bonus": statblock.initiative_bonus,
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
        return {
            "campaign": serialize_campaign(campaign),
            "permissions": {
                "can_manage_dm_content": can_manage_campaign_dm_content(campaign_slug),
            },
            "statblocks": [
                serialize_dm_statblock(statblock)
                for statblock in service.list_statblocks(campaign_slug)
            ],
            "conditions": [
                serialize_condition_definition(definition)
                for definition in service.list_condition_definitions(campaign_slug)
            ],
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
            "entry_type_label": entry_type_label(entry.entry_type),
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

    def normalize_source_ids(value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("source_ids must be an array of source IDs.")
        source_ids = [str(item or "").strip().upper() for item in value]
        source_ids = [item for item in source_ids if item]
        if not source_ids:
            raise ValueError("At least one source ID is required.")
        return source_ids

    def build_systems_index_payload(campaign_slug: str, *, query: str = "") -> dict[str, Any]:
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
                for entry in systems_service.search_entries_for_campaign(
                    campaign_slug,
                    query=search_query,
                    include_source_ids=include_source_ids,
                    limit=250,
                )
            ]
            if search_query
            else []
        )

        return {
            "campaign": serialize_campaign(campaign),
            "library": serialize_systems_library(systems_service.get_campaign_library(campaign_slug)),
            "query": search_query,
            "sources": [serialize_systems_source_state(campaign_slug, state) for state in source_states],
            "search_results": search_results,
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
        if campaign.system != SUPPORTED_COMBAT_SYSTEM:
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
        combat_system_supported = campaign.system == SUPPORTED_COMBAT_SYSTEM

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

        if combat_system_supported:
            combat_service = current_app.extensions["campaign_combat_service"]
            dm_content_service = current_app.extensions["campaign_dm_content_service"]
            tracker = combat_service.get_tracker(campaign_slug)
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

        return {
            "campaign": serialize_campaign(campaign),
            "combat_system_supported": combat_system_supported,
            "tracker": tracker_view,
            "available_character_choices": available_character_choices,
            "available_statblock_choices": available_statblock_choices,
            "combat_condition_options": combat_condition_options,
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

    def serialize_character_summary(record: CharacterRecord) -> dict[str, Any]:
        profile = dict(record.definition.profile or {})
        vitals = dict((record.state_record.state or {}).get("vitals") or {})
        return {
            "slug": record.definition.character_slug,
            "name": record.definition.name,
            "status": record.definition.status,
            "class_level_text": profile_class_level_text(profile, default=""),
            "species": str(profile.get("species") or ""),
            "background": str(profile.get("background") or ""),
            "current_hp": int(vitals.get("current_hp") or 0),
            "max_hp": int((record.definition.stats or {}).get("max_hp") or 0),
            "temp_hp": int(vitals.get("temp_hp") or 0),
            "revision": record.state_record.revision,
        }

    def serialize_character_record(campaign_slug: str, record: CharacterRecord) -> dict[str, Any]:
        return {
            "definition": record.definition.to_dict(),
            "import_metadata": record.import_metadata.to_dict(),
            "state_record": serialize_character_state(record.state_record),
            "permissions": {
                "can_edit_session": has_session_mode_access(campaign_slug, record.definition.character_slug),
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
            }
        )

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
                    "can_post_session_messages": can_post_campaign_session_messages(campaign_slug),
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
        return jsonify(
            {
                "ok": True,
                "pages": [serialize_page_file_summary(campaign_slug, record) for record in page_records],
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

        return jsonify({"ok": True, "page_file": serialize_page_file_record(campaign_slug, record)})

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
        return jsonify({"ok": True, "page_file": serialize_page_file_record(campaign_slug, refreshed_record)})

    @api.delete("/campaigns/<campaign_slug>/content/pages/<path:page_ref>")
    @api_campaign_content_management_required
    def content_page_delete(campaign_slug: str, page_ref: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        try:
            deleted = delete_campaign_page_file(
                campaign,
                page_ref,
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
        return jsonify({"ok": True, **build_systems_index_payload(campaign_slug, query=query)})

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

        book_entries = systems_service.list_entries_for_campaign_source(
            campaign_slug,
            source_id,
            entry_type="book",
            limit=None,
        )
        all_entry_groups = [
            {
                "entry_type": entry_type,
                "entry_type_label": entry_type_label(entry_type),
                "count": count,
            }
            for entry_type, count in systems_service.list_entry_type_counts_for_campaign_source(campaign_slug, source_id)
        ]
        all_entry_groups.sort(
            key=lambda item: (
                item["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
                *systems_entry_type_sort_key(item["entry_type"]),
            )
        )
        entry_groups = [
            item for item in all_entry_groups if item["entry_type"] not in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        ]

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

        entry_count = systems_service.count_entries_for_source(
            campaign_slug,
            source_id,
            entry_type=normalized_entry_type,
        )
        if entry_count <= 0:
            abort(404)

        query = request.args.get("q", "").strip()
        entries = systems_service.list_entries_for_campaign_source(
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
                "entry_type_label": entry_type_label(normalized_entry_type),
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
        return jsonify(
            {
                "ok": True,
                **build_session_payload(campaign_slug),
            }
        )

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
                    for message in session_service.list_messages(session_record.id)
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
            )
        except CampaignSessionValidationError as exc:
            return json_error(str(exc), 400, code="validation_error")

        return jsonify(
            {
                "ok": True,
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
                article = session_service.create_article(
                    campaign_slug,
                    title=markdown_upload.title,
                    body_markdown=markdown_upload.body_markdown,
                    created_by_user_id=user.id,
                )
                image_payload = payload.get("referenced_image")
                if markdown_upload.image_reference and image_payload is None:
                    raise CampaignSessionValidationError(
                        "This markdown file references an image. Include referenced_image too."
                    )
                if image_payload is not None:
                    image_file = decode_embedded_file(image_payload, label="referenced_image")
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=image_file["filename"],
                        media_type=image_file["media_type"],
                        data_blob=image_file["data_blob"],
                        alt_text=markdown_upload.image_alt,
                        caption=markdown_upload.image_caption,
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

                    source_body_markdown = page_record.body_markdown.strip() or page_record.page.summary.strip()
                    if not source_body_markdown:
                        raise CampaignSessionValidationError(
                            "The selected wiki page does not have any body text or summary to pull into the session store."
                        )

                    article = session_service.create_article(
                        campaign_slug,
                        title=page_record.page.title,
                        body_markdown=source_body_markdown,
                        source_page_ref=build_session_article_page_source_ref(page_record.page_ref),
                        created_by_user_id=user.id,
                    )
                    if page_record.page.image_path:
                        image_path = get_campaign_asset_file(campaign, page_record.page.image_path)
                        if image_path is not None:
                            media_type, _ = mimetypes.guess_type(image_path.name)
                            session_service.attach_article_image(
                                campaign_slug,
                                article.id,
                                filename=image_path.name,
                                media_type=media_type,
                                data_blob=image_path.read_bytes(),
                                alt_text=page_record.page.image_alt,
                                caption=page_record.page.image_caption,
                            )
            else:
                article = session_service.create_article(
                    campaign_slug,
                    title=payload.get("title", ""),
                    body_markdown=payload.get("body_markdown", ""),
                    created_by_user_id=user.id,
                )
                image_payload = payload.get("image")
                if image_payload is not None:
                    image_file = decode_embedded_file(image_payload, label="image")
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=image_file["filename"],
                        media_type=image_file["media_type"],
                        data_blob=image_file["data_blob"],
                        alt_text=str(image_payload.get("alt_text") or "").strip(),
                        caption=str(image_payload.get("caption") or "").strip(),
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

    @api.get("/campaigns/<campaign_slug>/dm-content")
    @api_campaign_scope_access_required("dm_content")
    def dm_content_state(campaign_slug: str):
        return jsonify({"ok": True, **build_dm_content_payload(campaign_slug)})

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
                created_by_user_id=user.id,
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

    @api.get("/campaigns/<campaign_slug>/combat")
    @api_campaign_scope_access_required("combat")
    def combat_state(campaign_slug: str):
        return jsonify({"ok": True, **build_combat_payload(campaign_slug)})

    @api.get("/campaigns/<campaign_slug>/combat/live-state")
    @api_campaign_scope_access_required("combat")
    def combat_live_state(campaign_slug: str):
        return jsonify({"ok": True, **build_combat_payload(campaign_slug, include_sidebar_choices=False)})

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
        if campaign.system != SUPPORTED_COMBAT_SYSTEM:
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

        statblock = current_app.extensions["campaign_dm_content_service"].get_statblock(campaign_slug, statblock_id)
        if statblock is None:
            return json_error("Choose a valid DM Content statblock to add.", 400, code="validation_error")

        try:
            current_app.extensions["campaign_combat_service"].add_npc_combatant(
                campaign_slug,
                display_name=str(payload.get("display_name") or "").strip() or statblock.title,
                turn_value=payload.get("turn_value") if payload.get("turn_value") not in (None, "") else statblock.initiative_bonus,
                initiative_bonus=statblock.initiative_bonus,
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
    @api_campaign_scope_access_required("characters")
    def character_list(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            abort(404)

        records = get_character_repository().list_visible_characters(campaign_slug)
        return jsonify(
            {
                "ok": True,
                "campaign": serialize_campaign(campaign),
                "characters": [serialize_character_summary(record) for record in records],
            }
        )

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>")
    @api_campaign_scope_access_required("characters")
    def character_detail(campaign_slug: str, character_slug: str):
        record = load_character_record(campaign_slug, character_slug)
        return jsonify({"ok": True, "character": serialize_character_record(campaign_slug, record)})

    @api.get("/campaigns/<campaign_slug>/characters/<character_slug>/rest-preview/<rest_type>")
    @api_campaign_scope_access_required("characters")
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
            forbidden_message="You do not have permission to use the Character page sheet edit view for this character.",
            conflict_message=(
                "This sheet changed before your batch save finished. Refresh and review the latest sheet before "
                "saving again. Session Character, Combat, or another tab may have changed nearby fields first; "
                "nothing was auto-merged."
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals")
    @api_campaign_scope_access_required("characters")
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
                hp_delta=payload.get("hp_delta"),
                temp_hp_delta=payload.get("temp_hp_delta"),
                clear_temp_hp=bool(payload.get("clear_temp_hp")),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>")
    @api_campaign_scope_access_required("characters")
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
    @api_campaign_scope_access_required("characters")
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
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_inventory_update(campaign_slug: str, character_slug: str, item_id: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_inventory_quantity(
                record,
                item_id,
                expected_revision=int(payload.get("expected_revision")),
                quantity=payload.get("quantity"),
                delta=payload.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/currency")
    @api_campaign_scope_access_required("characters")
    @api_login_required
    def character_currency_update(campaign_slug: str, character_slug: str):
        return run_character_mutation(
            campaign_slug,
            character_slug,
            lambda record, payload, user_id: get_character_state_service().update_currency(
                record,
                expected_revision=int(payload.get("expected_revision")),
                values={key: payload.get(key) for key in ("cp", "sp", "ep", "gp", "pp")},
                updated_by_user_id=user_id,
            ),
        )

    @api.patch("/campaigns/<campaign_slug>/characters/<character_slug>/session/notes")
    @api_campaign_scope_access_required("characters")
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
    @api_campaign_scope_access_required("characters")
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
