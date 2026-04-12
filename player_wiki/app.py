from __future__ import annotations

from collections import defaultdict
import hashlib
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import time

from flask import Flask, abort, flash, g, jsonify, make_response, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .admin import register_admin
from .api import register_api
from .auth import (
    can_access_campaign_scope,
    can_access_campaign_systems_entry,
    can_access_campaign_systems_source,
    can_manage_campaign_combat,
    can_manage_campaign_content,
    can_manage_campaign_dm_content,
    can_manage_campaign_systems,
    can_manage_campaign_visibility,
    can_manage_campaign_session,
    can_post_campaign_session_messages,
    campaign_systems_entry_access_required,
    campaign_systems_source_access_required,
    campaign_scope_access_required,
    clear_campaign_visibility_cache,
    get_accessible_campaign_entries,
    get_auth_store,
    get_current_user,
    get_current_user_preferences,
    get_effective_campaign_visibility,
    get_public_campaign_entries,
    has_session_mode_access,
    login_required,
    register_auth,
    role_satisfies_visibility,
)
from .character_builder import (
    CAMPAIGN_ITEMS_SECTION,
    CAMPAIGN_MECHANICS_SECTION,
    _build_item_catalog,
    _build_spell_catalog,
    _list_campaign_enabled_entries,
    CharacterBuildError,
    apply_imported_progression_repairs,
    build_native_level_up_context,
    build_native_level_up_character_definition,
    build_imported_progression_repair_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    native_level_up_readiness,
    supports_native_level_up,
)
from .character_editor import (
    CharacterEditValidationError,
    apply_character_spell_management_edit,
    apply_equipment_catalog_edit,
    apply_equipment_state_edit,
    apply_native_character_retraining,
    build_character_spell_management_context,
    apply_native_character_edits,
    build_managed_character_import_metadata,
    build_native_character_edit_context,
    build_native_character_retraining_context,
    search_character_spell_management_options,
)
from .character_importer import write_yaml
from .character_profile import ensure_profile_class_rows, profile_class_level_text, profile_class_rows, profile_primary_class_ref
from .character_service import CharacterStateValidationError, build_initial_state, merge_state_with_definition
from .combat_presenter import DND_5E_CONDITION_OPTIONS, present_combat_tracker
from .character_presenter import (
    build_character_entry_href,
    format_signed,
    present_character_detail,
    present_character_roster,
    render_campaign_markdown,
)
from .auth_store import AuthStore
from .campaign_combat_service import CampaignCombatService, CampaignCombatValidationError
from .campaign_combat_store import CampaignCombatStore
from .campaign_content_service import (
    delete_campaign_asset_file,
    delete_campaign_character_file,
    write_campaign_asset_file,
)
from .campaign_dm_content_service import CampaignDMContentService, CampaignDMContentValidationError
from .campaign_dm_content_store import CampaignDMContentStore
from .campaign_page_store import CampaignPageStore
from .campaign_session_service import (
    ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS,
    CampaignSessionService,
    CampaignSessionValidationError,
)
from .campaign_session_store import CampaignSessionStore
from .character_repository import CharacterRepository, load_campaign_character_config
from .character_state_service import CharacterStateService
from .character_store import CharacterStateConflictError, CharacterStateStore
from .campaign_visibility import (
    CAMPAIGN_VISIBILITY_SCOPE_LABELS,
    CAMPAIGN_VISIBILITY_SCOPES,
    DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE,
    VISIBILITY_LABELS,
    VISIBILITY_PRIVATE,
    is_valid_visibility,
    list_visibility_choices,
    normalize_visibility_choice,
)
from .config import Config
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
)
from .db import get_db_query_metrics, register_db, reset_db_query_metrics
from .models import section_sort_key, subsection_sort_key
from .session_article_publisher import (
    SessionArticlePublishError,
    build_default_publish_options,
    find_published_page_for_session_article,
    list_published_pages_for_session_articles,
    list_section_choices,
    normalize_publish_options,
    publish_session_article,
)
from .repository import Repository, normalize_lookup, slugify
from .repository_store import RepositoryStore
from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
    parse_session_article_source_ref,
)
from .session_presenter import (
    present_session_articles,
    present_session_log_summaries,
    present_session_messages,
    present_session_record,
)
from .systems_service import LICENSE_CLASS_LABELS, SystemsPolicyValidationError, SystemsService
from .systems_store import SystemsStore
from .version import build_app_metadata

SESSION_ARTICLE_FORM_MODES = {"manual", "upload", "wiki"}
CHARACTER_READ_SUBPAGE_LABELS = {
    "quick": "Quick Reference",
    "spellcasting": "Spellcasting",
    "features": "Features",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "personal": "Personal",
    "notes": "Notes",
}
CHARACTER_CONTROLS_SUBPAGE_LABELS = {
    "controls": "Controls",
}
COMBAT_SUBPAGE_LABELS = {
    "combat": "Combat",
    "character": "Character",
    "status": "Status",
    "dm": "DM page",
}
COMBAT_SOURCE_LABELS = {
    COMBAT_SOURCE_KIND_CHARACTER: "Character",
    COMBAT_SOURCE_KIND_MANUAL_NPC: "Manual NPC",
    COMBAT_SOURCE_KIND_DM_STATBLOCK: "DM Content",
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER: "Systems",
}
BUILDER_RELEVANT_CAMPAIGN_SECTIONS = frozenset(
    {
        CAMPAIGN_MECHANICS_SECTION,
        CAMPAIGN_ITEMS_SECTION,
    }
)
SUPPORTED_COMBAT_SYSTEM = "DND-5E"
SUPPORTED_NATIVE_CHARACTER_SYSTEM = "DND-5E"
NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE = (
    "Native character tools are currently only supported for DND-5E campaigns."
)
CHARACTER_PORTRAIT_ALT_MAX_LENGTH = 200
CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH = 300
CHARACTER_PORTRAIT_MAX_BYTES = 8 * 1024 * 1024
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


def systems_entry_type_sort_key(entry_type: str) -> tuple[int, str]:
    try:
        return (SYSTEMS_ENTRY_TYPE_ORDER.index(entry_type), entry_type)
    except ValueError:
        return (len(SYSTEMS_ENTRY_TYPE_ORDER), entry_type)


def normalize_session_article_form_mode(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in SESSION_ARTICLE_FORM_MODES:
        return normalized
    return "manual"


def get_character_read_subpage_labels(
    *,
    include_spellcasting: bool = False,
    include_controls: bool = False,
) -> dict[str, str]:
    labels = {
        "quick": CHARACTER_READ_SUBPAGE_LABELS["quick"],
    }
    if include_spellcasting:
        labels["spellcasting"] = CHARACTER_READ_SUBPAGE_LABELS["spellcasting"]
    labels.update(
        {
            "features": CHARACTER_READ_SUBPAGE_LABELS["features"],
            "equipment": CHARACTER_READ_SUBPAGE_LABELS["equipment"],
            "inventory": CHARACTER_READ_SUBPAGE_LABELS["inventory"],
            "personal": CHARACTER_READ_SUBPAGE_LABELS["personal"],
            "notes": CHARACTER_READ_SUBPAGE_LABELS["notes"],
        }
    )
    if include_controls:
        labels.update(CHARACTER_CONTROLS_SUBPAGE_LABELS)
    return labels


def normalize_character_read_subpage(
    value: str,
    *,
    include_spellcasting: bool = False,
    include_controls: bool = False,
) -> str:
    normalized = (value or "").strip().lower()
    if normalized in get_character_read_subpage_labels(
        include_spellcasting=include_spellcasting,
        include_controls=include_controls,
    ):
        return normalized
    return "quick"


def normalize_combat_return_view(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "dm":
        return normalized
    return "combat"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    campaign_page_store = CampaignPageStore()
    repository_store = RepositoryStore(
        app.config["CAMPAIGNS_DIR"],
        page_store=campaign_page_store,
        reload_enabled=app.config["RELOAD_CONTENT"],
        scan_interval_seconds=app.config["CONTENT_SCAN_INTERVAL_SECONDS"],
    )
    auth_store = AuthStore()
    character_state_store = CharacterStateStore()
    campaign_session_store = CampaignSessionStore()
    campaign_combat_store = CampaignCombatStore()
    campaign_dm_content_store = CampaignDMContentStore()
    systems_store = SystemsStore()
    character_repository = CharacterRepository(app.config["CAMPAIGNS_DIR"], character_state_store)
    character_state_service = CharacterStateService(character_state_store)
    campaign_session_service = CampaignSessionService(campaign_session_store)
    campaign_combat_service = CampaignCombatService(
        campaign_combat_store,
        character_repository,
        character_state_service,
        player_snapshot_sync_interval_seconds=app.config[
            "COMBAT_PLAYER_SNAPSHOT_SYNC_INTERVAL_SECONDS"
        ],
    )
    campaign_dm_content_service = CampaignDMContentService(campaign_dm_content_store)
    systems_service = SystemsService(systems_store, repository_store)

    app.extensions["repository_store"] = repository_store
    app.extensions["campaign_page_store"] = campaign_page_store
    app.extensions["auth_store"] = auth_store
    app.extensions["character_state_store"] = character_state_store
    app.extensions["campaign_session_store"] = campaign_session_store
    app.extensions["campaign_combat_store"] = campaign_combat_store
    app.extensions["campaign_dm_content_store"] = campaign_dm_content_store
    app.extensions["systems_store"] = systems_store
    app.extensions["character_repository"] = character_repository
    app.extensions["character_state_service"] = character_state_service
    app.extensions["campaign_session_service"] = campaign_session_service
    app.extensions["campaign_combat_service"] = campaign_combat_service
    app.extensions["campaign_dm_content_service"] = campaign_dm_content_service
    app.extensions["systems_service"] = systems_service
    register_db(app)
    register_auth(app)
    register_admin(app)
    register_api(app)

    if app.config["TRUST_PROXY"]:
        hops = app.config["PROXY_FIX_HOPS"]
        app.wsgi_app = ProxyFix(  # type: ignore[assignment]
            app.wsgi_app,
            x_for=hops,
            x_proto=hops,
            x_host=hops,
            x_port=hops,
            x_prefix=hops,
        )

    if app.config["APP_ENV"] == "production" and app.config["SECRET_KEY"] == "development-only-secret-key":
        app.logger.warning("PLAYER_WIKI_SECRET_KEY is using the default development value.")

    @app.before_request
    def start_live_request_diagnostics():
        if not app.config["LIVE_DIAGNOSTICS"]:
            return None
        reset_db_query_metrics()
        g.live_request_started_at = time.perf_counter()
        return None

    before_request_chain = app.before_request_funcs.setdefault(None, [])
    if before_request_chain and before_request_chain[-1] is start_live_request_diagnostics:
        before_request_chain.insert(0, before_request_chain.pop())

    def get_repository() -> Repository:
        return repository_store.get()

    def get_campaign_page_store() -> CampaignPageStore:
        return campaign_page_store

    def list_builder_campaign_page_records(campaign_slug: str, campaign) -> list[object]:
        return [
            page_record
            for page_record in get_campaign_page_store().list_page_records(campaign_slug)
            if campaign.is_page_visible(page_record.page)
            and str(page_record.page.section or "").strip() in BUILDER_RELEVANT_CAMPAIGN_SECTIONS
        ]

    def get_character_repository() -> CharacterRepository:
        return character_repository

    def get_character_state_service() -> CharacterStateService:
        return character_state_service

    def get_campaign_session_service() -> CampaignSessionService:
        return campaign_session_service

    def get_campaign_combat_service() -> CampaignCombatService:
        return campaign_combat_service

    def get_campaign_dm_content_service() -> CampaignDMContentService:
        return campaign_dm_content_service

    def get_systems_service() -> SystemsService:
        return systems_service

    def get_campaign_asset_file(campaign, asset_path: str) -> Path | None:
        normalized_asset_path = asset_path.strip().replace("\\", "/")
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

        entry = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, normalized_entry_slug)
        if entry is None or not can_access_campaign_systems_entry(campaign_slug, entry.slug):
            return None
        return entry

    def can_player_access_campaign_scope(campaign_slug: str, scope: str) -> bool:
        if get_repository().get_campaign(campaign_slug) is None:
            return False
        return role_satisfies_visibility(
            "player",
            get_effective_campaign_visibility(campaign_slug, scope),
        )

    def get_player_visible_session_wiki_page_record(
        campaign_slug: str,
        page_ref: str,
    ):
        campaign = load_campaign_context(campaign_slug)
        if not can_player_access_campaign_scope(campaign_slug, "wiki"):
            return None
        return get_pullable_session_wiki_page_record(campaign, page_ref)

    def build_player_session_wiki_search_results(
        campaign_slug: str,
        query: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, str]]:
        campaign = load_campaign_context(campaign_slug)
        normalized_query = query.strip()
        if len(normalized_query) < 2 or not can_player_access_campaign_scope(campaign_slug, "wiki"):
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
            subtitle = " / ".join(part for part in context_parts if part)
            results.append(
                {
                    "page_ref": record.page_ref,
                    "title": record.page.title,
                    "subtitle": subtitle,
                    "select_label": f"{record.page.title} - {subtitle}" if subtitle else record.page.title,
                }
            )
            if len(results) >= limit:
                break
        return results

    def build_player_session_wiki_lookup_preview_context(
        campaign_slug: str,
        page_ref: str,
    ) -> dict[str, object] | None:
        campaign = load_campaign_context(campaign_slug)
        page_record = get_player_visible_session_wiki_page_record(campaign_slug, page_ref)
        if page_record is None:
            return None

        body_html = get_repository().get_page_body_html(campaign.slug, page_record.page.route_slug)
        if body_html is None:
            return None
        body_html = body_html.replace(
            "/campaigns/{campaign_slug}/",
            f"/campaigns/{campaign.slug}/",
        )

        page_image_url = None
        if (
            page_record.page.image_path
            and get_campaign_asset_file(campaign, page_record.page.image_path) is not None
        ):
            page_image_url = url_for(
                "campaign_asset",
                campaign_slug=campaign.slug,
                asset_path=page_record.page.image_path,
            )

        return {
            "lookup_page": page_record.page,
            "lookup_page_url": url_for(
                "page_view",
                campaign_slug=campaign.slug,
                page_slug=page_record.page.route_slug,
            ),
            "lookup_page_image_url": page_image_url,
            "lookup_body_html": body_html,
        }

    def build_session_article_source_search_results(campaign_slug: str, query: str, *, limit: int = 30) -> list[dict[str, str]]:
        campaign = load_campaign_context(campaign_slug)
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
            systems_entries = get_systems_service().search_entries_for_campaign(
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
                        "subtitle": f"{SYSTEMS_ENTRY_TYPE_LABELS.get(entry.entry_type, entry.entry_type.replace('_', ' ').title())} - {entry.source_id}",
                        "kind_label": "Systems",
                        "select_label": (
                            f"{entry.title} - Systems - "
                            f"{SYSTEMS_ENTRY_TYPE_LABELS.get(entry.entry_type, entry.entry_type.replace('_', ' ').title())} - "
                            f"{entry.source_id}"
                        ),
                    }
                )
                if len(results) >= limit:
                    break

        return results

    def load_character_context(campaign_slug: str, character_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if not campaign:
            abort(404)

        record = get_character_repository().get_visible_character(campaign_slug, character_slug)
        if record is None:
            abort(404)
        return campaign, record

    def load_campaign_context(campaign_slug: str):
        campaign = get_repository().get_campaign(campaign_slug)
        if not campaign:
            abort(404)
        return campaign

    def build_character_controls_context(campaign_slug: str, character_slug: str):
        store = get_auth_store()
        user = get_current_user()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        assigned_user = store.get_user_by_id(assignment.user_id) if assignment is not None else None
        can_assign_owner = bool(user and user.is_admin)
        can_delete_character = can_manage_campaign_content(campaign_slug)

        player_choices: list[dict[str, object]] = []
        if can_assign_owner:
            for candidate in sorted(
                store.list_users(),
                key=lambda item: ((item.display_name or "").lower(), item.email.lower()),
            ):
                if not candidate.is_active:
                    continue
                membership = store.get_membership(candidate.id, campaign_slug, statuses=("active",))
                if membership is None or membership.role != "player":
                    continue
                player_choices.append(
                    {
                        "user_id": candidate.id,
                        "label": f"{candidate.display_name} ({candidate.email})",
                        "is_current": bool(assignment and assignment.user_id == candidate.id),
                    }
                )

        return {
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
            "can_delete_character": can_delete_character,
            "current_user_is_owner": bool(user and assignment and assignment.user_id == user.id),
            "player_choices": player_choices,
        }

    def normalize_character_page_ref(value: object) -> str:
        if isinstance(value, dict):
            slug = str(value.get("slug") or value.get("page_slug") or "").strip()
            if slug:
                return slug
        return str(value or "").strip()

    CHARACTER_ITEMS_SECTION = "Items"

    def filter_character_page_records(
        campaign_page_records: list[object],
        *,
        section: str | None = None,
        include_page_refs: set[str] | None = None,
    ) -> list[object]:
        normalized_section = str(section or "").strip()
        normalized_include_page_refs = {
            normalize_character_page_ref(value)
            for value in set(include_page_refs or set())
            if normalize_character_page_ref(value)
        }
        filtered_records: list[object] = []
        for page_record in list(campaign_page_records or []):
            page_ref = str(getattr(page_record, "page_ref", "") or "").strip()
            page = getattr(page_record, "page", None)
            if not page_ref or page is None:
                continue
            if normalized_section:
                page_section = str(getattr(page, "section", "") or "").strip()
                if page_section != normalized_section and page_ref not in normalized_include_page_refs:
                    continue
            filtered_records.append(page_record)
        return filtered_records

    def build_character_page_link_options(
        campaign_page_records: list[object],
        *,
        section: str | None = None,
        include_page_refs: set[str] | None = None,
    ) -> list[dict[str, str]]:
        options: list[dict[str, str]] = []
        for page_record in filter_character_page_records(
            campaign_page_records,
            section=section,
            include_page_refs=include_page_refs,
        ):
            page_ref = str(getattr(page_record, "page_ref", "") or "").strip()
            page = getattr(page_record, "page", None)
            if not page_ref or page is None:
                continue
            context_parts = [
                str(getattr(page, "section", "") or "").strip(),
                str(getattr(page, "subsection", "") or "").strip(),
            ]
            context_label = " / ".join(part for part in context_parts if part)
            title = str(getattr(page, "title", "") or page_ref).strip()
            options.append(
                {
                    "value": page_ref,
                    "label": f"{title} - {context_label}" if context_label else title,
                }
            )
        return options

    def list_visible_character_page_records(campaign_slug: str, campaign) -> list[object]:
        return [
            page_record
            for page_record in get_campaign_page_store().list_page_records(campaign_slug)
            if campaign.is_page_visible(page_record.page)
            and str(page_record.page.section or "").strip() != "Sessions"
        ]

    def list_visible_character_item_page_records(
        campaign_slug: str,
        campaign,
        *,
        include_page_refs: set[str] | None = None,
    ) -> list[object]:
        return filter_character_page_records(
            list_visible_character_page_records(campaign_slug, campaign),
            section=CHARACTER_ITEMS_SECTION,
            include_page_refs=include_page_refs,
        )

    def format_character_systems_item_weight(value: object) -> str:
        if value in (None, ""):
            return ""
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return str(value).strip()
        if numeric_value <= 0:
            return ""
        if numeric_value.is_integer():
            return f"{int(numeric_value)} lb."
        return f"{numeric_value:g} lb."

    def build_character_systems_ref(entry) -> dict[str, str]:
        return {
            "entry_key": str(entry.entry_key or "").strip(),
            "entry_type": str(entry.entry_type or "").strip(),
            "title": str(entry.title or "").strip(),
            "slug": str(entry.slug or "").strip(),
            "source_id": str(entry.source_id or "").strip(),
        }

    def build_character_inventory_item_ref(item: object) -> str:
        payload = dict(item or {}) if isinstance(item, dict) else {}
        return str(payload.get("catalog_ref") or payload.get("id") or "").strip()

    def systems_item_requires_attunement(value: object) -> bool:
        if value in (None, "", False, [], {}):
            return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized or normalized in {"false", "none", "no", "not required"}:
                return False
        return True

    def build_character_item_catalog(campaign_slug: str) -> dict[str, object]:
        return _build_item_catalog(
            _list_campaign_enabled_entries(
                get_systems_service(),
                campaign_slug,
                "item",
            )
        )

    def build_character_inventory_manager_context(
        campaign_slug: str,
        campaign,
        record,
        *,
        campaign_page_records: list[object],
    ) -> dict[str, object]:
        campaign_item_page_options = build_character_page_link_options(
            campaign_page_records,
            section=CHARACTER_ITEMS_SECTION,
        )
        inventory_by_ref = {
            build_character_inventory_item_ref(item): dict(item)
            for item in list((record.state_record.state or {}).get("inventory") or [])
            if build_character_inventory_item_ref(item)
        }
        supplemental_items: list[dict[str, object]] = []
        for item in list(record.definition.equipment_catalog or []):
            if str(item.get("source_kind") or "").strip() != "manual_edit":
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                continue
            inventory_item = inventory_by_ref.get(item_id, {})
            systems_ref = dict(item.get("systems_ref") or {})
            page_ref = normalize_character_page_ref(item.get("page_ref"))
            item_page_options = build_character_page_link_options(
                campaign_page_records,
                section=CHARACTER_ITEMS_SECTION,
                include_page_refs={page_ref} if page_ref else None,
            )
            quantity_value = inventory_item.get("quantity")
            default_quantity = item.get("default_quantity")
            supplemental_items.append(
                {
                    "id": item_id,
                    "name": str(item.get("name") or "Item").strip(),
                    "quantity": int(quantity_value if quantity_value is not None else default_quantity or 0),
                    "weight": str(item.get("weight") or "").strip(),
                    "notes": str(item.get("notes") or "").strip(),
                    "page_ref": page_ref,
                    "href": build_character_entry_href(
                        campaign.slug,
                        systems_ref=systems_ref,
                        page_ref=item.get("page_ref"),
                    ),
                    "is_systems_item": bool(systems_ref),
                    "is_campaign_item": bool(page_ref and not systems_ref),
                    "page_options": item_page_options,
                    "source_label": (
                        f"Systems item ({systems_ref.get('source_id') or 'Unknown source'})"
                        if systems_ref
                        else "Campaign item"
                        if page_ref
                        else "Custom item"
                    ),
                }
            )
        return {
            "search_url": url_for(
                "character_equipment_systems_item_search",
                campaign_slug=campaign_slug,
                character_slug=record.definition.character_slug,
            ),
            "campaign_item_page_options": campaign_item_page_options,
            "supplemental_items": sorted(
                supplemental_items,
                key=lambda item: (str(item["name"]).lower(), str(item["id"]).lower()),
            ),
        }

    def build_character_equipment_state_context(
        campaign_slug: str,
        campaign,
        record,
    ) -> dict[str, object]:
        systems_service = get_systems_service()
        definition_item_lookup = {
            str(item.get("id") or "").strip(): dict(item)
            for item in list(record.definition.equipment_catalog or [])
            if str(item.get("id") or "").strip()
        }
        equipment_items: list[dict[str, object]] = []
        for inventory_item in list((record.state_record.state or {}).get("inventory") or []):
            item_ref = build_character_inventory_item_ref(inventory_item)
            if not item_ref:
                continue
            definition_item = definition_item_lookup.get(item_ref, {})
            systems_ref = dict(definition_item.get("systems_ref") or {})
            page_ref = normalize_character_page_ref(definition_item.get("page_ref"))
            systems_entry = None
            entry_slug = str(systems_ref.get("slug") or "").strip()
            if entry_slug and str(systems_ref.get("entry_type") or "").strip() == "item":
                systems_entry = systems_service.get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
            requires_attunement = systems_item_requires_attunement(
                ((systems_entry.metadata or {}).get("attunement") if systems_entry is not None else None)
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
                    "href": build_character_entry_href(
                        campaign.slug,
                        systems_ref=systems_ref,
                        page_ref=definition_item.get("page_ref"),
                    ),
                    "is_equipped": bool(inventory_item.get("is_equipped", False)),
                    "is_attuned": bool(inventory_item.get("is_attuned", False)),
                    "requires_attunement": requires_attunement,
                    "attunement_hint": (
                        "Requires attunement"
                        if requires_attunement
                        else "Use attunement only when the item's rules call for it."
                    ),
                    "source_label": (
                        f"Systems item ({systems_ref.get('source_id') or 'Unknown source'})"
                        if systems_ref
                        else "Campaign item"
                        if page_ref
                        else "Custom item"
                        if str(definition_item.get("source_kind") or "").strip() == "manual_edit"
                        else "Sheet item"
                    ),
                }
            )
        max_attuned_items = int(
            ((record.state_record.state or {}).get("attunement") or {}).get("max_attuned_items") or 3
        )
        attuned_count = sum(1 for item in equipment_items if bool(item.get("is_attuned")))
        equipped_count = sum(1 for item in equipment_items if bool(item.get("is_equipped")))
        return {
            "rows": equipment_items,
            "attuned_count": attuned_count,
            "equipped_count": equipped_count,
            "max_attuned_items": max_attuned_items,
            "at_attunement_limit": attuned_count >= max_attuned_items if max_attuned_items > 0 else True,
            "over_attunement_limit": attuned_count > max_attuned_items,
        }

    def resolve_character_spellcasting_class_entries(campaign_slug: str, definition) -> list[dict[str, object]]:
        spellcasting_rows = [dict(row or {}) for row in list((definition.spellcasting or {}).get("class_rows") or []) if isinstance(row, dict)]
        profile_rows = ensure_profile_class_rows(definition.profile)
        profile_rows_by_id = {
            str(row.get("row_id") or "").strip() or f"class-row-{index}": dict(row or {})
            for index, row in enumerate(profile_rows, start=1)
        }
        results: list[dict[str, object]] = []
        candidate_rows = spellcasting_rows or [
            {
                "class_row_id": str(row.get("row_id") or "").strip() or f"class-row-{index}",
                "class_ref": dict(row.get("systems_ref") or {}),
            }
            for index, row in enumerate(profile_rows, start=1)
        ]
        for index, row in enumerate(candidate_rows, start=1):
            row_id = str(row.get("class_row_id") or row.get("row_id") or "").strip() or f"class-row-{index}"
            profile_row = dict(profile_rows_by_id.get(row_id) or {})
            systems_ref = dict(row.get("class_ref") or row.get("systems_ref") or {})
            if str(systems_ref.get("entry_type") or "").strip() != "class":
                continue
            entry_slug = str(systems_ref.get("slug") or "").strip()
            if not entry_slug:
                continue
            entry = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
            if entry is None or str(entry.entry_type or "").strip() != "class":
                continue
            selected_subclass = None
            subclass_slug = str(dict(profile_row.get("subclass_ref") or {}).get("slug") or "").strip()
            if subclass_slug:
                selected_subclass = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, subclass_slug)
                if selected_subclass is not None and str(selected_subclass.entry_type or "").strip() != "subclass":
                    selected_subclass = None
            results.append(
                {
                    "class_row_id": row_id,
                    "row_id": row_id,
                    "row_level": int(profile_row.get("level") or row.get("level") or 0),
                    "selected_class": entry,
                    "selected_subclass": selected_subclass,
                }
            )
        if not results:
            profile = dict(definition.profile or {})
            systems_ref = profile_primary_class_ref(profile) or dict(profile.get("class_ref") or {})
            entry_slug = str(dict(systems_ref or {}).get("slug") or "").strip()
            if entry_slug:
                entry = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
                if entry is not None and str(entry.entry_type or "").strip() == "class":
                    first_profile_row = dict((profile_rows or [{}])[0] or {})
                    selected_subclass = None
                    subclass_slug = str(dict(first_profile_row.get("subclass_ref") or {}).get("slug") or "").strip()
                    if subclass_slug:
                        selected_subclass = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, subclass_slug)
                        if selected_subclass is not None and str(selected_subclass.entry_type or "").strip() != "subclass":
                            selected_subclass = None
                    results.append(
                        {
                            "class_row_id": "class-row-1",
                            "row_id": "class-row-1",
                            "row_level": int(first_profile_row.get("level") or 0),
                            "selected_class": entry,
                            "selected_subclass": selected_subclass,
                        }
                    )
        return results

    def load_character_spell_management_support(campaign_slug: str, definition) -> tuple[dict[str, object], list[dict[str, object]]]:
        spell_catalog = _build_spell_catalog(
            _list_campaign_enabled_entries(
                get_systems_service(),
                campaign_slug,
                "spell",
            )
        )
        selected_class_rows = resolve_character_spellcasting_class_entries(campaign_slug, definition)
        return spell_catalog, selected_class_rows

    def build_character_spell_manager_context(
        campaign_slug: str,
        campaign,
        record,
    ) -> dict[str, object] | None:
        spell_catalog, selected_class_rows = load_character_spell_management_support(campaign_slug, record.definition)
        manager = build_character_spell_management_context(
            record.definition,
            spell_catalog=spell_catalog,
            selected_class_rows=selected_class_rows,
        )
        if manager is None:
            return None

        sections: list[dict[str, object]] = []
        for section in list(manager.get("sections") or []):
            section_payload = dict(section or {})
            if section_payload.get("spell_attack_bonus") not in {"", None}:
                section_payload["spell_attack_bonus"] = format_signed(section_payload.get("spell_attack_bonus"))
            rows: list[dict[str, object]] = []
            for row in list(section_payload.get("rows") or []):
                payload = dict(row.get("payload") or {})
                rows.append(
                    {
                        **dict(row),
                        "href": build_character_entry_href(
                            campaign.slug,
                            systems_ref=payload.get("systems_ref"),
                            page_ref=payload.get("page_ref"),
                        ),
                        "casting_time": str(payload.get("casting_time") or "").strip(),
                        "range": str(payload.get("range") or "").strip(),
                        "duration": str(payload.get("duration") or "").strip(),
                        "components": str(payload.get("components") or "").strip(),
                        "save_or_hit": str(payload.get("save_or_hit") or "").strip(),
                        "source": str(payload.get("source") or "").strip(),
                        "reference": str(payload.get("reference") or "").strip(),
                    }
                )
            section_payload["rows"] = rows
            sections.append(section_payload)

        return {
            **manager,
            "sections": sections,
            "search_url": url_for(
                "character_spell_search",
                campaign_slug=campaign_slug,
                character_slug=record.definition.character_slug,
            ),
            "add_url": url_for(
                "character_spell_add",
                campaign_slug=campaign_slug,
                character_slug=record.definition.character_slug,
            ),
            "update_url": url_for(
                "character_spell_update",
                campaign_slug=campaign_slug,
                character_slug=record.definition.character_slug,
            ),
            "remove_url": url_for(
                "character_spell_remove",
                campaign_slug=campaign_slug,
                character_slug=record.definition.character_slug,
            ),
        }

    def build_character_spellcasting_placeholder(spell_manager: dict[str, object]) -> dict[str, object] | None:
        sections = [dict(section or {}) for section in list(spell_manager.get("sections") or []) if isinstance(section, dict)]
        if not sections:
            return None
        primary_section = dict(sections[0] or {})
        row_sections = [
            {
                "class_row_id": str(section.get("class_row_id") or "").strip(),
                "title": str(section.get("title") or "Spellcasting").strip() or "Spellcasting",
                "spellcasting_ability": str(section.get("spellcasting_ability") or "").strip(),
                "spell_save_dc": section.get("spell_save_dc"),
                "spell_attack_bonus": str(section.get("spell_attack_bonus") or "").strip(),
                "counts": list(section.get("counts") or []),
                "spells": [],
            }
            for section in sections
        ]
        return {
            "spellcasting_class": str(primary_section.get("title") or "Spellcasting").strip() or "Spellcasting",
            "spellcasting_ability": str(primary_section.get("spellcasting_ability") or "").strip(),
            "spell_save_dc": primary_section.get("spell_save_dc"),
            "spell_attack_bonus": str(primary_section.get("spell_attack_bonus") or "").strip(),
            "slots": [],
            "slots_title": "",
            "slot_pools": [],
            "multiclass_summary": "",
            "row_sections": row_sections,
            "is_multiclass": len(row_sections) > 1,
        }

    def build_character_portrait_asset_ref(character_slug: str, filename: str) -> str:
        extension = Path(filename).suffix.lower()
        return f"characters/{character_slug}/portrait{extension}"

    def validate_character_portrait_upload(upload) -> tuple[str, bytes]:
        filename = Path(str(getattr(upload, "filename", "") or "").strip()).name
        if not filename:
            raise ValueError("Choose an image file before saving the portrait.")
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS:
            raise ValueError("Character portraits must be PNG, JPG, GIF, or WEBP files.")
        data_blob = upload.read() if upload is not None else b""
        if not data_blob:
            raise ValueError("Uploaded portrait files cannot be empty.")
        if len(data_blob) > CHARACTER_PORTRAIT_MAX_BYTES:
            raise ValueError("Character portraits must stay under 8 MB.")
        return filename, data_blob

    def build_character_portrait_context(campaign, definition) -> dict[str, str] | None:
        profile = dict(definition.profile or {})
        asset_ref = str(profile.get("portrait_asset_ref") or "").strip()
        if not asset_ref:
            return None
        if get_campaign_asset_file(campaign, asset_ref) is None:
            return None
        return {
            "asset_ref": asset_ref,
            "url": url_for(
                "character_portrait_asset",
                campaign_slug=campaign.slug,
                character_slug=definition.character_slug,
            ),
            "alt": str(profile.get("portrait_alt") or definition.name).strip() or definition.name,
            "caption": str(profile.get("portrait_caption") or "").strip(),
        }

    def update_character_portrait_profile(
        definition,
        *,
        asset_ref: str = "",
        alt_text: str = "",
        caption: str = "",
    ):
        payload = definition.to_dict()
        profile = dict(payload.get("profile") or {})
        clean_asset_ref = str(asset_ref or "").strip()
        clean_alt_text = str(alt_text or "").strip()
        clean_caption = str(caption or "").strip()
        if clean_asset_ref:
            profile["portrait_asset_ref"] = clean_asset_ref
            profile["portrait_alt"] = clean_alt_text
            profile["portrait_caption"] = clean_caption
        else:
            profile.pop("portrait_asset_ref", None)
            profile.pop("portrait_alt", None)
            profile.pop("portrait_caption", None)
        payload["profile"] = profile
        return definition.__class__.from_dict(payload)

    def redirect_to_character_mode(campaign_slug: str, character_slug: str, *, anchor: str | None = None):
        _, record = load_character_context(campaign_slug, character_slug)
        spellcasting_payload = dict(record.definition.spellcasting or {})
        read_subpage = normalize_character_read_subpage(
            request.values.get("page", ""),
            include_spellcasting=bool(
                spellcasting_payload.get("spells")
                or spellcasting_payload.get("slot_progression")
                or spellcasting_payload.get("slot_lanes")
            ),
            include_controls=has_session_mode_access(campaign_slug, character_slug),
        )
        mode = request.values.get("mode", "").strip().lower()
        route_values = {
            "campaign_slug": campaign_slug,
            "character_slug": character_slug,
            "page": read_subpage,
            "_anchor": anchor,
        }
        if mode == "session":
            route_values["mode"] = mode
        return redirect(
            url_for("character_read_view", **route_values)
        )

    def redirect_to_character_controls(
        campaign_slug: str,
        character_slug: str,
        *,
        anchor: str | None = None,
    ):
        route_values = {
            "campaign_slug": campaign_slug,
            "character_slug": character_slug,
            "page": "controls",
            "_anchor": anchor,
        }
        requested_mode = request.values.get("mode", "").strip().lower()
        if requested_mode == "session" and has_session_mode_access(campaign_slug, character_slug):
            route_values["mode"] = requested_mode
        return redirect(url_for("character_read_view", **route_values))

    def redirect_to_campaign_session(
        campaign_slug: str,
        *,
        anchor: str | None = None,
        article_mode: str | None = None,
    ):
        return redirect(
            url_for(
                "campaign_session_view",
                campaign_slug=campaign_slug,
                article_mode=article_mode,
                _anchor=anchor,
            )
        )

    def redirect_to_campaign_session_dm(
        campaign_slug: str,
        *,
        anchor: str | None = None,
        article_mode: str | None = None,
    ):
        return redirect(
            url_for(
                "campaign_session_dm_view",
                campaign_slug=campaign_slug,
                article_mode=article_mode,
                _anchor=anchor,
            )
        )

    def redirect_to_campaign_combat(
        campaign_slug: str,
        *,
        anchor: str | None = None,
        combatant_id: int | None = None,
    ):
        return redirect(
            url_for(
                "campaign_combat_view",
                campaign_slug=campaign_slug,
                combatant=combatant_id,
                _anchor=anchor,
            )
        )

    def redirect_to_campaign_combat_dm(
        campaign_slug: str,
        *,
        anchor: str | None = None,
        combatant_id: int | None = None,
    ):
        return redirect(
            url_for(
                "campaign_combat_dm_view",
                campaign_slug=campaign_slug,
                combatant=combatant_id,
                _anchor=anchor,
            )
        )

    def redirect_to_campaign_combat_status(
        campaign_slug: str,
        *,
        anchor: str | None = None,
        combatant_id: int | None = None,
    ):
        return redirect(
            url_for(
                "campaign_combat_status_view",
                campaign_slug=campaign_slug,
                combatant=combatant_id,
                _anchor=anchor,
            )
        )

    def redirect_to_campaign_combat_character(
        campaign_slug: str,
        *,
        anchor: str | None = None,
        combatant_id: int | None = None,
    ):
        return redirect(
            url_for(
                "campaign_combat_character_view",
                campaign_slug=campaign_slug,
                combatant=combatant_id,
                _anchor=anchor,
            )
        )

    def redirect_to_campaign_dm_content(
        campaign_slug: str,
        *,
        anchor: str | None = None,
    ):
        return redirect(
            url_for(
                "campaign_dm_content_view",
                campaign_slug=campaign_slug,
                _anchor=anchor,
            )
        )

    def is_async_request() -> bool:
        return request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"

    def render_flash_stack_html() -> str:
        return render_template("_flash_stack.html")

    def build_live_hash(*parts: object) -> str:
        normalized_parts = [str(part) for part in parts]
        digest = hashlib.sha1("||".join(normalized_parts).encode("utf-8")).hexdigest()
        return digest[:12]

    def build_combat_live_view_token(
        campaign_slug: str,
        combat_subpage: str,
        *,
        selected_combatant_id: int | None = None,
    ) -> str:
        return build_live_hash(
            "combat",
            combat_subpage,
            "1" if can_manage_campaign_combat(campaign_slug) else "0",
            str(selected_combatant_id or ""),
            *sorted(get_owned_character_slugs(campaign_slug)),
        )

    def normalize_session_subpage(value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "dm":
            return "dm"
        return "session"

    def build_session_live_view_token(campaign_slug: str, session_subpage: str) -> str:
        normalized_subpage = normalize_session_subpage(session_subpage)
        current_preferences = get_current_user_preferences()
        return build_live_hash(
            "session",
            normalized_subpage,
            current_preferences.session_chat_order,
            "1" if can_manage_campaign_session(campaign_slug) else "0",
            "1" if can_post_campaign_session_messages(campaign_slug) else "0",
        )

    def build_combat_poll_settings(combat_subpage: str) -> dict[str, int]:
        if combat_subpage == "status":
            return {
                "active_interval_ms": 1500,
                "idle_interval_ms": 4000,
                "idle_threshold_ms": 30000,
            }
        return {
            "active_interval_ms": 1000,
            "idle_interval_ms": 3000,
            "idle_threshold_ms": 30000,
        }

    def build_session_poll_settings(session_subpage: str) -> dict[str, int]:
        if session_subpage == "dm":
            return {
                "active_interval_ms": 2000,
                "idle_interval_ms": 5000,
                "idle_threshold_ms": 30000,
            }
        return {
            "active_interval_ms": 3000,
            "idle_interval_ms": 6000,
            "idle_threshold_ms": 30000,
        }

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

    def should_short_circuit_live_response(
        *,
        live_revision: int,
        live_view_token: str,
    ) -> bool:
        requested_revision = parse_live_revision_header()
        requested_view_token = parse_live_view_token_header()
        if requested_revision is None or not requested_view_token:
            return False
        return requested_revision == live_revision and requested_view_token == live_view_token

    def build_unchanged_live_payload(
        *,
        live_revision: int,
        live_view_token: str,
    ) -> dict[str, object]:
        return {
            "changed": False,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
        }

    def attach_live_response_diagnostics(
        response,
        *,
        view_name: str,
        changed: bool,
        state_check_ms: float,
        render_ms: float,
        live_revision: int | None = None,
    ):
        query_metrics = get_db_query_metrics()
        query_count = int(query_metrics["query_count"] or 0)
        query_time_ms = float(query_metrics["query_time_ms"] or 0.0)
        request_started_at = getattr(g, "live_request_started_at", None)
        request_time_ms = (
            (time.perf_counter() - request_started_at) * 1000
            if isinstance(request_started_at, float)
            else state_check_ms + render_ms
        )
        payload_bytes = len(response.get_data())
        live_response_summary = {
            "view": view_name,
            "path": request.full_path.rstrip("?"),
            "changed": changed,
            "live_revision": live_revision,
            "query_count": query_count,
            "query_time_ms": round(query_time_ms, 2),
            "request_time_ms": round(request_time_ms, 2),
            "state_check_ms": round(state_check_ms, 2),
            "render_ms": round(render_ms, 2),
            "payload_bytes": payload_bytes,
        }
        slow_log_threshold_ms = float(app.config.get("LIVE_SLOW_LOG_THRESHOLD_MS") or 0.0)

        if app.config["LIVE_DIAGNOSTICS"]:
            server_timing_parts = [
                f"state-check;dur={state_check_ms:.2f}",
                f"db;dur={query_time_ms:.2f}",
                f"render;dur={render_ms:.2f}",
                f"total;dur={request_time_ms:.2f}",
            ]
            response.headers["Server-Timing"] = ", ".join(server_timing_parts)
            response.headers["X-Live-State-Changed"] = "true" if changed else "false"
            if live_revision is not None:
                response.headers["X-Live-Revision"] = str(live_revision)
            response.headers["X-Live-Payload-Bytes"] = str(payload_bytes)
            response.headers["X-Live-Query-Count"] = str(query_count)
            response.headers["X-Live-Query-Time-Ms"] = f"{query_time_ms:.2f}"
            response.headers["X-Live-Request-Time-Ms"] = f"{request_time_ms:.2f}"
            response.headers["X-Live-View"] = view_name
            app.logger.info("live_response %s", json.dumps(live_response_summary, sort_keys=True))

        if slow_log_threshold_ms > 0 and request_time_ms >= slow_log_threshold_ms:
            app.logger.warning("slow_live_response %s", json.dumps(live_response_summary, sort_keys=True))
        return response

    def build_live_json_response(
        payload: dict[str, object],
        *,
        view_name: str,
        changed: bool,
        live_revision: int | None,
        state_check_ms: float,
        render_ms: float,
    ):
        response = jsonify(payload)
        return attach_live_response_diagnostics(
            response,
            view_name=view_name,
            changed=changed,
            live_revision=live_revision,
            state_check_ms=state_check_ms,
            render_ms=render_ms,
        )

    def build_combat_live_metadata(
        campaign_slug: str,
        combat_subpage: str,
        *,
        selected_combatant_id: int | None = None,
    ) -> dict[str, object]:
        combat_service = get_campaign_combat_service()
        combat_service.sync_player_character_snapshots(campaign_slug)
        if selected_combatant_id is None:
            selected_combatant_id = parse_requested_combatant_id()
        return {
            "live_revision": combat_service.get_live_revision(campaign_slug),
            "live_view_token": build_combat_live_view_token(
                campaign_slug,
                combat_subpage,
                selected_combatant_id=selected_combatant_id,
            ),
        }

    def build_session_live_metadata(campaign_slug: str, session_subpage: str) -> dict[str, object]:
        session_service = get_campaign_session_service()
        return {
            "live_revision": session_service.get_live_revision(campaign_slug),
            "live_view_token": build_session_live_view_token(campaign_slug, session_subpage),
        }

    def build_session_manager_state_token(
        *,
        active_session_id: int | None,
        staged_articles: list[dict[str, object]],
        revealed_articles: list[dict[str, object]],
        session_logs: list[dict[str, object]],
    ) -> str:
        staged_ids = ",".join(str(article["id"]) for article in staged_articles)
        revealed_ids = ",".join(str(article["id"]) for article in revealed_articles)
        log_ids = ",".join(str(log["id"]) for log in session_logs)
        return f"{active_session_id or 0}|{staged_ids}|{revealed_ids}|{log_ids}"

    def build_combat_live_state_token(tracker_view: dict[str, object]) -> str:
        combatants = tracker_view.get("combatants", [])
        parts = [
            str(tracker_view.get("round_number", "")),
            str(tracker_view.get("current_turn_label", "")),
            str(tracker_view.get("combatant_count", "")),
        ]
        for combatant in combatants:
            conditions = combatant.get("conditions", [])
            condition_text = ",".join(
                f"{condition['id']}:{condition['name']}:{condition['duration_text']}"
                for condition in conditions
            )
            parts.append(
                "|".join(
                    [
                        str(combatant.get("id", "")),
                        str(combatant.get("turn_value", "")),
                        str(combatant.get("current_hp", "")),
                        str(combatant.get("max_hp", "")),
                        str(combatant.get("temp_hp", "")),
                        str(combatant.get("movement_total", "")),
                        str(combatant.get("movement_remaining", "")),
                        "1" if combatant.get("has_action") else "0",
                        "1" if combatant.get("has_bonus_action") else "0",
                        "1" if combatant.get("has_reaction") else "0",
                        "1" if combatant.get("is_current_turn") else "0",
                        condition_text,
                    ]
                )
            )
        return "||".join(parts)

    def build_selected_combatant_state_token(
        tracker_view: dict[str, object],
        selected_combatant: dict[str, object] | None,
    ) -> str:
        if not selected_combatant:
            return ""
        return build_combat_live_state_token(
            {
                "round_number": tracker_view.get("round_number", 1),
                "current_turn_label": tracker_view.get("current_turn_label", ""),
                "combatant_count": 1,
                "combatants": [selected_combatant],
            }
        )

    def parse_expected_revision() -> int:
        raw_value = request.form.get("expected_revision", "").strip()
        if not raw_value:
            raise ValueError("Missing sheet revision. Refresh the page and try again.")
        return int(raw_value)

    def get_owned_character_slugs(campaign_slug: str) -> set[str]:
        user = get_current_user()
        if user is None:
            return set()
        assignments = get_auth_store().list_character_assignments_for_user(
            user.id,
            campaign_slug=campaign_slug,
        )
        return {assignment.character_slug for assignment in assignments}

    def build_combat_route_values(
        campaign_slug: str,
        *,
        selected_combatant_id: int | None = None,
        selected_character_slug: str | None = None,
    ) -> dict[str, object]:
        route_values: dict[str, object] = {"campaign_slug": campaign_slug}
        if selected_combatant_id is not None:
            route_values["combatant"] = selected_combatant_id
        elif selected_character_slug:
            route_values["character"] = selected_character_slug
        return route_values

    def parse_requested_combatant_id(
        *,
        raw_value: str | None = None,
        strict: bool = False,
    ) -> int | None:
        normalized = (raw_value if raw_value is not None else request.args.get("combatant", "")).strip()
        if not normalized:
            return None
        try:
            return int(normalized)
        except ValueError:
            if strict:
                abort(404)
            return None

    def get_requested_combatant_id_from_values() -> int | None:
        return parse_requested_combatant_id(raw_value=request.values.get("combatant", ""))

    def resolve_selected_tracker_combatant(
        tracker_view: dict[str, object],
        combatants: list[object],
        *,
        explicit_combatant_id: int | None = None,
        strict_explicit: bool = False,
    ) -> tuple[object | None, dict[str, object] | None]:
        combatants_by_id = {combatant.id: combatant for combatant in combatants if getattr(combatant, "id", None) is not None}
        presented_combatants_by_id = {
            int(combatant["id"]): combatant
            for combatant in list(tracker_view.get("combatants") or [])
            if combatant.get("id") is not None
        }

        if explicit_combatant_id is not None:
            combatant_record = combatants_by_id.get(explicit_combatant_id)
            presented_combatant = presented_combatants_by_id.get(explicit_combatant_id)
            if combatant_record is not None and presented_combatant is not None:
                return combatant_record, presented_combatant
            if strict_explicit:
                abort(404)

        current_turn_id = next(
            (
                int(combatant["id"])
                for combatant in list(tracker_view.get("combatants") or [])
                if combatant.get("is_current_turn")
            ),
            None,
        )
        if current_turn_id is not None:
            combatant_record = combatants_by_id.get(current_turn_id)
            presented_combatant = presented_combatants_by_id.get(current_turn_id)
            if combatant_record is not None and presented_combatant is not None:
                return combatant_record, presented_combatant

        if combatants:
            first_combatant = combatants[0]
            presented_combatant = presented_combatants_by_id.get(first_combatant.id)
            if presented_combatant is not None:
                return first_combatant, presented_combatant

        return None, None

    def list_accessible_combat_character_rows(
        combatants: list[object],
        tracker_view: dict[str, object],
        character_records_by_slug: dict[str, object],
        *,
        campaign_slug: str,
        can_manage_combat: bool,
        owned_character_slugs: set[str] | None = None,
    ) -> list[dict[str, object]]:
        if can_manage_combat:
            return []
        owned_character_slugs = owned_character_slugs if owned_character_slugs is not None else get_owned_character_slugs(
            campaign_slug
        )
        presented_combatants_by_id = {
            int(combatant["id"]): combatant
            for combatant in list(tracker_view.get("combatants") or [])
            if combatant.get("id") is not None
        }
        rows = []
        for combatant in combatants:
            if not combatant.is_player_character or not combatant.character_slug:
                continue
            if combatant.character_slug not in owned_character_slugs:
                continue
            record = character_records_by_slug.get(combatant.character_slug)
            presented_combatant = presented_combatants_by_id.get(combatant.id)
            if record is None or presented_combatant is None:
                continue
            rows.append(
                {
                    "combatant_record": combatant,
                    "combatant": presented_combatant,
                    "record": record,
                }
            )
        return rows

    def build_combat_subpages(
        campaign_slug: str,
        *,
        current_subpage: str,
        include_character_subpage: bool = True,
        selected_combatant_id: int | None = None,
        selected_character_combatant_id: int | None = None,
        selected_character_slug: str | None = None,
    ) -> list[dict[str, object]]:
        focused_route_values = build_combat_route_values(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
        )
        character_route_values = build_combat_route_values(
            campaign_slug,
            selected_combatant_id=(
                selected_character_combatant_id
                if selected_character_combatant_id is not None
                else selected_combatant_id
            ),
            selected_character_slug=selected_character_slug,
        )

        subpages = [
            {
                "slug": "combat",
                "label": COMBAT_SUBPAGE_LABELS["combat"],
                "href": url_for("campaign_combat_view", **focused_route_values),
                "is_active": current_subpage == "combat",
            },
        ]
        if include_character_subpage:
            subpages.append(
                {
                    "slug": "character",
                    "label": COMBAT_SUBPAGE_LABELS["character"],
                    "href": url_for("campaign_combat_character_view", **character_route_values),
                    "is_active": current_subpage == "character",
                }
            )
        if can_manage_campaign_combat(campaign_slug):
            subpages.append(
                {
                    "slug": "status",
                    "label": COMBAT_SUBPAGE_LABELS["status"],
                    "href": url_for("campaign_combat_status_view", **focused_route_values),
                    "is_active": current_subpage == "status",
                }
            )
            subpages.append(
                {
                    "slug": "dm",
                    "label": COMBAT_SUBPAGE_LABELS["dm"],
                    "href": url_for("campaign_combat_dm_view", **focused_route_values),
                    "is_active": current_subpage == "dm",
                }
            )
        return subpages

    def require_supported_combat_system(campaign_slug: str):
        campaign = load_campaign_context(campaign_slug)
        if campaign.system != SUPPORTED_COMBAT_SYSTEM:
            flash(
                f"Combat tracker support for {campaign.system or 'this system'} is not available yet.",
                "error",
            )
            return None
        return campaign

    def campaign_supports_native_character_tools(campaign) -> bool:
        return (
            str(getattr(campaign, "system", "") or "").strip().upper()
            == SUPPORTED_NATIVE_CHARACTER_SYSTEM
        )

    def redirect_unsupported_native_character_tools(
        campaign_slug: str,
        *,
        character_slug: str | None = None,
    ):
        flash(NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE, "error")
        if character_slug is None:
            return redirect(url_for("character_roster_view", campaign_slug=campaign_slug))
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    def merge_condition_options(*option_sets: list[str] | tuple[str, ...]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for option_set in option_sets:
            for option in option_set:
                normalized = normalize_lookup(str(option or ""))
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                merged.append(str(option).strip())
        return merged

    def render_character_page(
        campaign_slug: str,
        character_slug: str,
        *,
        notes_draft: str | None = None,
        physical_description_draft: str | None = None,
        background_draft: str | None = None,
        force_session_mode: bool = False,
        status_code: int = 200,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        native_character_tools_supported = campaign_supports_native_character_tools(campaign)
        can_use_session_mode = has_session_mode_access(campaign_slug, character_slug)
        can_manage_character = can_manage_campaign_session(campaign_slug)
        campaign_page_records = list_visible_character_page_records(campaign_slug, campaign)
        retraining_page_records = (
            [
                page_record
                for page_record in get_campaign_page_store().list_page_records(campaign_slug)
                if page_record.page.published
                and page_record.page.reveal_after_session <= campaign.current_session
                and str(page_record.page.section or "").strip() != "Sessions"
            ]
            if can_use_session_mode and native_character_tools_supported
            else []
        )
        level_up_readiness = (
            native_level_up_readiness(
                get_systems_service(),
                campaign_slug,
                record.definition,
                campaign_page_records=campaign_page_records,
            )
            if can_manage_character and native_character_tools_supported
            else None
        )
        can_level_up = bool(level_up_readiness and level_up_readiness.get("status") == "ready")
        can_retrain = False
        if retraining_page_records:
            retraining_context = build_native_character_retraining_context(
                record.definition,
                campaign_page_records=retraining_page_records,
                optionalfeature_catalog={
                    str(entry.slug or "").strip(): entry
                    for entry in _list_campaign_enabled_entries(
                        app.extensions["systems_service"],
                        campaign_slug,
                        "optionalfeature",
                    )
                    if str(entry.slug or "").strip()
                },
                spell_catalog=_build_spell_catalog(
                    _list_campaign_enabled_entries(
                        app.extensions["systems_service"],
                        campaign_slug,
                        "spell",
                    )
                ),
            )
            can_retrain = bool(retraining_context.get("feature_rows"))
        include_controls_subpage = can_use_session_mode
        requested_mode = request.args.get("mode", "").strip().lower()
        is_session_mode = force_session_mode or (requested_mode == "session" and can_use_session_mode)

        confirm_rest = request.args.get("confirm_rest", "").strip().lower() if is_session_mode else ""
        rest_preview = None
        if confirm_rest in {"short", "long"}:
            rest_preview = get_character_state_service().preview_rest(record, confirm_rest)

        character = present_character_detail(
            campaign,
            record,
            include_player_notes_section=not is_session_mode,
            systems_service=get_systems_service(),
        )
        if notes_draft is not None:
            character["player_notes_markdown"] = notes_draft
        if physical_description_draft is not None:
            character["physical_description_markdown"] = physical_description_draft
        if background_draft is not None:
            character["personal_background_markdown"] = background_draft
        character["portrait"] = build_character_portrait_context(campaign, record.definition)
        spell_manager = build_character_spell_manager_context(campaign_slug, campaign, record)
        if not character.get("spellcasting") and spell_manager is not None:
            spellcasting_placeholder = build_character_spellcasting_placeholder(spell_manager)
            if spellcasting_placeholder is not None:
                character["spellcasting"] = spellcasting_placeholder
        include_spellcasting_subpage = bool(character.get("spellcasting"))
        available_character_subpages = get_character_read_subpage_labels(
            include_spellcasting=include_spellcasting_subpage,
            include_controls=include_controls_subpage,
        )
        character_subpage = normalize_character_read_subpage(
            request.args.get("page", ""),
            include_spellcasting=include_spellcasting_subpage,
            include_controls=include_controls_subpage,
        )

        character_controls = (
            build_character_controls_context(campaign_slug, character_slug)
            if include_controls_subpage
            else None
        )
        inventory_manager = (
            build_character_inventory_manager_context(
                campaign_slug,
                campaign,
                record,
                campaign_page_records=campaign_page_records,
            )
            if can_use_session_mode
            else None
        )
        equipment_state_manager = build_character_equipment_state_context(
            campaign_slug,
            campaign,
            record,
        )
        character_subpages = [
            {
                "slug": slug,
                "label": label,
                "href": url_for(
                    "character_read_view",
                    campaign_slug=campaign.slug,
                    character_slug=character["slug"],
                    mode="session" if is_session_mode else None,
                    page=slug,
                ),
                "is_active": slug == character_subpage,
            }
            for slug, label in available_character_subpages.items()
        ]

        return (
            render_template(
                "character_read.html",
                campaign=campaign,
                character=character,
                character_subpage=character_subpage,
                character_subpages=character_subpages,
                active_nav="characters",
                can_use_session_mode=can_use_session_mode,
                native_character_tools_supported=native_character_tools_supported,
                can_level_up=can_level_up,
                can_retrain=can_retrain,
                level_up_readiness=level_up_readiness,
                is_session_mode=is_session_mode,
                rest_preview=rest_preview,
                character_controls=character_controls,
                inventory_manager=inventory_manager,
                equipment_state_manager=equipment_state_manager,
                spell_manager=spell_manager,
            ),
            status_code,
        )

    def run_character_definition_mutation(
        campaign_slug: str,
        character_slug: str,
        *,
        anchor: str,
        success_message: str,
        action,
    ):
        _, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            result = action(record)
            inventory_state_overrides = None
            if isinstance(result, tuple) and len(result) == 4:
                definition, import_metadata, inventory_quantity_overrides, inventory_state_overrides = result
            else:
                definition, import_metadata, inventory_quantity_overrides = result
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                inventory_quantity_overrides=inventory_quantity_overrides,
                inventory_state_overrides=inventory_state_overrides,
            )
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterEditValidationError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash(success_message, "success")

        return redirect_to_character_mode(campaign_slug, character_slug, anchor=anchor)

    def render_character_builder_page(
        campaign_slug: str,
        builder_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        def _parse_live_builder_regions() -> list[str]:
            raw_regions = str(request.args.get("regions") or "").strip()
            if not raw_regions:
                return []
            regions: list[str] = []
            seen_regions: set[str] = set()
            for region_id in raw_regions.split(","):
                normalized_region_id = str(region_id or "").strip()
                if not normalized_region_id or normalized_region_id in seen_regions:
                    continue
                seen_regions.add(normalized_region_id)
                regions.append(normalized_region_id)
            return regions

        campaign = load_campaign_context(campaign_slug)
        builder_ready = bool(
            builder_context.get("class_options")
            and builder_context.get("species_options")
            and builder_context.get("background_options")
        )
        is_live_preview = request.method == "GET" and request.args.get("_live_preview") == "1"
        requested_regions = _parse_live_builder_regions() if is_live_preview else []
        template_name = (
            "_character_create_builder_regions.html"
            if requested_regions
            else "_character_create_builder.html"
            if is_live_preview
            else "character_create.html"
        )
        render_started_at = time.perf_counter()
        response = make_response(
            render_template(
                template_name,
                campaign=campaign,
                builder=builder_context,
                builder_ready=builder_ready,
                active_nav="characters",
                live_diagnostics_enabled=app.config["LIVE_DIAGNOSTICS"],
                requested_regions=requested_regions,
            ),
            status_code,
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        if is_live_preview:
            return attach_live_response_diagnostics(
                response,
                view_name="builder-create",
                changed=True,
                live_revision=None,
                state_check_ms=0.0,
                render_ms=render_ms,
            )
        return response

    def render_character_edit_page(
        campaign_slug: str,
        character_slug: str,
        edit_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        return (
            render_template(
                "character_edit.html",
                campaign=campaign,
                character=present_character_detail(
                    campaign,
                    record,
                    include_player_notes_section=True,
                    systems_service=get_systems_service(),
                ),
                edit_context=edit_context,
                active_nav="characters",
            ),
            status_code,
        )

    def render_character_retraining_page(
        campaign_slug: str,
        character_slug: str,
        retraining_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        return (
            render_template(
                "character_retraining.html",
                campaign=campaign,
                character=present_character_detail(
                    campaign,
                    record,
                    include_player_notes_section=True,
                    systems_service=get_systems_service(),
                ),
                retraining_context=retraining_context,
                active_nav="characters",
            ),
            status_code,
        )

    def render_character_level_up_page(
        campaign_slug: str,
        character_slug: str,
        level_up_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        def _parse_live_builder_regions() -> list[str]:
            raw_regions = str(request.args.get("regions") or "").strip()
            if not raw_regions:
                return []
            regions: list[str] = []
            seen_regions: set[str] = set()
            for region_id in raw_regions.split(","):
                normalized_region_id = str(region_id or "").strip()
                if not normalized_region_id or normalized_region_id in seen_regions:
                    continue
                seen_regions.add(normalized_region_id)
                regions.append(normalized_region_id)
            return regions

        campaign = load_campaign_context(campaign_slug)
        is_live_preview = request.method == "GET" and request.args.get("_live_preview") == "1"
        requested_regions = _parse_live_builder_regions() if is_live_preview else []
        template_name = (
            "_character_level_up_builder_regions.html"
            if requested_regions
            else "_character_level_up_builder.html"
            if is_live_preview
            else "character_level_up.html"
        )
        render_started_at = time.perf_counter()
        response = make_response(
            render_template(
                template_name,
                campaign=campaign,
                character_slug=character_slug,
                level_up=level_up_context,
                active_nav="characters",
                live_diagnostics_enabled=app.config["LIVE_DIAGNOSTICS"],
                requested_regions=requested_regions,
            ),
            status_code,
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        if is_live_preview:
            return attach_live_response_diagnostics(
                response,
                view_name="builder-level-up",
                changed=True,
                live_revision=None,
                state_check_ms=0.0,
                render_ms=render_ms,
            )
        return response

    def render_character_progression_repair_page(
        campaign_slug: str,
        character_slug: str,
        repair_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign = load_campaign_context(campaign_slug)
        return (
            render_template(
                "character_progression_repair.html",
                campaign=campaign,
                character_slug=character_slug,
                repair=repair_context,
                active_nav="characters",
            ),
            status_code,
        )

    def run_session_mutation(
        campaign_slug: str,
        character_slug: str,
        *,
        anchor: str,
        success_message: str,
        action,
    ):
        _, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            action(record, expected_revision, user.id)
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash(success_message, "success")

        return redirect_to_character_mode(campaign_slug, character_slug, anchor=anchor)

    def run_combat_character_mutation(
        campaign_slug: str,
        combatant_id: int,
        *,
        anchor: str,
        success_message: str,
        action,
    ):
        combatant = get_campaign_combat_service().get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            abort(404)
        if not combatant.is_player_character or not combatant.character_slug:
            abort(404)
        if combatant.character_slug not in get_owned_character_slugs(campaign_slug):
            abort(403)

        record = get_character_repository().get_visible_character(campaign_slug, combatant.character_slug)
        if record is None:
            abort(404)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            action(record, expected_revision, user.id)
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash(success_message, "success")

        return redirect_to_campaign_combat_character(
            campaign_slug,
            combatant_id=combatant_id,
            anchor=anchor,
        )

    def build_campaign_session_page_context(
        campaign_slug: str,
        *,
        session_subpage: str = "session",
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        session_service = get_campaign_session_service()
        can_manage_session = can_manage_campaign_session(campaign_slug)
        can_post_messages = can_post_campaign_session_messages(campaign_slug)
        session_article_form_mode = normalize_session_article_form_mode(
            request.args.get("article_mode", "manual")
        )
        all_articles = session_service.list_articles(campaign_slug)
        article_images = session_service.list_article_images([article.id for article in all_articles])
        converted_pages = list_published_pages_for_session_articles(
            campaign,
            [article.id for article in all_articles],
        )
        source_items: dict[int, dict[str, str]] = {}
        for article in all_articles:
            source_kind, source_ref = parse_session_article_source_ref(article.source_page_ref)
            if source_kind == SESSION_ARTICLE_SOURCE_KIND_PAGE and source_ref:
                page_record = get_campaign_page_store().get_page_record(
                    campaign.slug,
                    source_ref,
                    include_body=False,
                )
                source_items[article.id] = {
                    "label": "published wiki page",
                    "action_label": "View published page",
                    "missing_message": "The original published wiki page is not currently visible in the player wiki.",
                    "title": page_record.page.title if page_record is not None else "",
                    "url": (
                        url_for("page_view", campaign_slug=campaign.slug, page_slug=page_record.page.route_slug)
                        if page_record is not None and campaign.is_page_visible(page_record.page)
                        else ""
                    ),
                }
            elif source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS and source_ref:
                systems_entry = get_pullable_session_systems_entry(campaign_slug, source_ref)
                source_items[article.id] = {
                    "label": "Systems entry",
                    "action_label": "View Systems entry",
                    "missing_message": "The original Systems entry is not currently visible in this campaign.",
                    "title": systems_entry.title if systems_entry is not None else "",
                    "url": (
                        url_for(
                            "campaign_systems_entry_detail",
                            campaign_slug=campaign.slug,
                            entry_slug=systems_entry.slug,
                        )
                        if systems_entry is not None
                        else ""
                    ),
                }
        image_url_builder = lambda article_id: url_for(
            "campaign_session_article_image",
            campaign_slug=campaign.slug,
            article_id=article_id,
        )
        page_url_builder = lambda page_slug: url_for(
            "page_view",
            campaign_slug=campaign.slug,
            page_slug=page_slug,
        )

        active_session_record = session_service.get_active_session(campaign_slug)
        session_messages = []
        active_session = None
        if active_session_record is not None:
            live_messages = session_service.list_messages(active_session_record.id)
            session_messages = present_session_messages(
                campaign,
                live_messages,
                all_articles,
                article_images,
                image_url_builder=image_url_builder,
            )
            active_session = present_session_record(active_session_record, message_count=len(live_messages))

        staged_articles = []
        revealed_articles = []
        session_logs = []
        if can_manage_session:
            all_articles = session_service.list_articles(campaign_slug)
            staged_articles = present_session_articles(
                campaign,
                [article for article in all_articles if not article.is_revealed],
                article_images,
                image_url_builder=image_url_builder,
                converted_pages=converted_pages,
                source_items=source_items,
                page_url_builder=page_url_builder,
            )
            revealed_articles = present_session_articles(
                campaign,
                [article for article in all_articles if article.is_revealed],
                article_images,
                image_url_builder=image_url_builder,
                converted_pages=converted_pages,
                source_items=source_items,
                page_url_builder=page_url_builder,
            )
            session_logs = present_session_log_summaries(
                session_service.list_session_logs(campaign_slug, limit=12)
            )
        normalized_session_subpage = normalize_session_subpage(session_subpage)
        session_poll_settings = build_session_poll_settings(normalized_session_subpage)
        session_live_revision = session_service.get_live_revision(campaign_slug)
        session_live_view_token = build_session_live_view_token(campaign_slug, normalized_session_subpage)

        return {
            "campaign": campaign,
            "active_session": active_session,
            "active_session_id": active_session_record.id if active_session_record is not None else None,
            "session_messages": session_messages,
            "staged_articles": staged_articles,
            "revealed_articles": revealed_articles,
            "session_logs": session_logs,
            "can_manage_session": can_manage_session,
            "can_post_messages": can_post_messages,
            "chat_is_open": active_session is not None,
            "session_article_form_mode": session_article_form_mode,
            "session_manager_state_token": build_session_manager_state_token(
                active_session_id=active_session_record.id if active_session_record is not None else None,
                staged_articles=staged_articles,
                revealed_articles=revealed_articles,
                session_logs=session_logs,
            ),
            "session_live_revision": session_live_revision,
            "session_live_view_token": session_live_view_token,
            "live_diagnostics_enabled": app.config["LIVE_DIAGNOSTICS"],
            "session_poll_active_interval_ms": session_poll_settings["active_interval_ms"],
            "session_poll_idle_interval_ms": session_poll_settings["idle_interval_ms"],
            "session_poll_idle_threshold_ms": session_poll_settings["idle_threshold_ms"],
            "session_subpage": normalized_session_subpage,
            "active_nav": "session",
        }

    def build_combat_character_detail_context(campaign_slug: str, campaign, record) -> dict[str, object]:
        character_detail = present_character_detail(
            campaign,
            record,
            include_player_notes_section=False,
            systems_service=get_systems_service(),
        )
        overview_stats = [
            stat
            for stat in list(character_detail.get("overview_stats") or [])
            if stat.get("label") not in {"Current HP", "Temp HP"}
        ]
        selected_character_slug = record.definition.character_slug
        return {
            "selected_combat_character": character_detail,
            "selected_combat_overview_stats": overview_stats,
            "can_view_full_character_sheet": bool(selected_character_slug)
            and can_access_campaign_scope(campaign_slug, "characters"),
            "full_character_sheet_url": (
                url_for(
                    "character_read_view",
                    campaign_slug=campaign.slug,
                    character_slug=selected_character_slug,
                )
                if selected_character_slug
                else ""
            ),
        }

    def build_campaign_combat_page_context(
        campaign_slug: str,
        *,
        include_control_choices: bool = False,
        combat_subpage: str = "combat",
        selected_combatant_id: int | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        requested_combatant_id = (
            selected_combatant_id
            if selected_combatant_id is not None
            else parse_requested_combatant_id()
        )
        campaign = load_campaign_context(campaign_slug)
        can_manage_combat = can_manage_campaign_combat(campaign_slug)
        combat_system_supported = campaign.system == SUPPORTED_COMBAT_SYSTEM
        can_access_dm_content = can_access_campaign_scope(campaign_slug, "dm_content")
        can_access_systems = can_access_campaign_scope(campaign_slug, "systems")

        tracker_view = {
            "round_number": 1,
            "current_turn_label": "",
            "has_current_turn": False,
            "combatant_count": 0,
            "combatants": [],
        }
        available_character_choices: list[dict[str, str]] = []
        available_statblock_choices: list[dict[str, str]] = []
        combat_condition_options = list(DND_5E_CONDITION_OPTIONS)
        character_records_by_slug = {}
        combatants = []
        conditions_by_combatant: dict[int, list[object]] = {}
        selected_combatant_record = None
        selected_combatant = None
        combat_tracker_display_combatants: list[dict[str, object]] = []
        combat_tracker_section_title = "Turn order"
        combat_tracker_section_meta = "Highest turn value acts first. The current-turn badge marks the active combatant."
        dm_focus_combatant_choices: list[dict[str, object]] = []

        if combat_system_supported:
            combat_service = get_campaign_combat_service()
            dm_content_service = get_campaign_dm_content_service()
            combatants = combat_service.list_combatants(
                campaign_slug,
                sync_player_character_snapshots=sync_player_character_snapshots,
            )
            tracker = combat_service.get_tracker(campaign_slug)
            for combatant in combatants:
                if not combatant.character_slug:
                    continue
                record = get_character_repository().get_visible_character(campaign_slug, combatant.character_slug)
                if record is not None:
                    character_records_by_slug[combatant.character_slug] = record
            conditions_by_combatant = combat_service.list_conditions_by_combatant(campaign_slug)

            tracker_view = present_combat_tracker(
                tracker,
                combatants,
                conditions_by_combatant,
                character_records_by_slug=character_records_by_slug,
                owned_character_slugs=get_owned_character_slugs(campaign_slug),
                can_manage_combat=can_manage_combat,
            )

            if can_manage_combat and include_control_choices:
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

            combat_condition_options = merge_condition_options(
                DND_5E_CONDITION_OPTIONS,
                [condition.name for condition in dm_content_service.list_condition_definitions(campaign_slug)],
            )

            selected_combatant_record, selected_combatant = resolve_selected_tracker_combatant(
                tracker_view,
                combatants,
                explicit_combatant_id=requested_combatant_id,
                strict_explicit=False,
            )
            combat_tracker_display_combatants = list(tracker_view.get("combatants") or [])
        combat_poll_settings = build_combat_poll_settings(combat_subpage)
        combat_live_revision = tracker.revision if combat_system_supported else 0

        selected_combatant_id = (
            selected_combatant_record.id if selected_combatant_record is not None else None
        )
        if combat_subpage == "dm":
            requested_combatant_id = selected_combatant_id
            dm_focus_combatant_choices = [
                {
                    "id": combatant.get("id"),
                    "label": " - ".join(
                        part
                        for part in [
                            str(combatant.get("name") or "").strip(),
                            str(combatant.get("type_label") or "").strip(),
                            f"Turn {combatant.get('turn_value')}",
                            "Current turn" if combatant.get("is_current_turn") else "",
                        ]
                        if part
                    ),
                }
                for combatant in list(tracker_view.get("combatants") or [])
                if combatant.get("id") is not None
            ]
            combat_tracker_display_combatants = [selected_combatant] if selected_combatant is not None else []
            combat_tracker_section_title = "Selected combatant"
            combat_tracker_section_meta = (
                "Choose a combatant from the focus picker above to inspect and edit one participant at a time."
            )
        combat_live_view_token = build_combat_live_view_token(
            campaign_slug,
            combat_subpage,
            selected_combatant_id=requested_combatant_id,
        )
        accessible_combat_character_rows = list_accessible_combat_character_rows(
            combatants,
            tracker_view,
            character_records_by_slug,
            campaign_slug=campaign_slug,
            can_manage_combat=can_manage_combat,
        )
        selected_combat_character_row = next(
            (
                row
                for row in accessible_combat_character_rows
                if row["combatant_record"].id == selected_combatant_id
            ),
            None,
        )
        combat_character_entry_row = selected_combat_character_row
        if combat_character_entry_row is None and accessible_combat_character_rows:
            combat_character_entry_row = accessible_combat_character_rows[0]
        selected_character_combatant_id = (
            combat_character_entry_row["combatant_record"].id
            if combat_character_entry_row is not None
            else None
        )
        selected_character_slug = (
            combat_character_entry_row["record"].definition.character_slug
            if combat_character_entry_row is not None
            else ""
        )
        selected_combatant_character_url = (
            url_for(
                "campaign_combat_character_view",
                campaign_slug=campaign.slug,
                combatant=selected_combat_character_row["combatant_record"].id,
            )
            if selected_combat_character_row is not None
            else ""
        )
        combat_character_entry_url = (
            url_for(
                "campaign_combat_character_view",
                campaign_slug=campaign.slug,
                combatant=selected_character_combatant_id,
            )
            if selected_character_combatant_id is not None
            else ""
        )
        selected_combatant_status_url = (
            url_for(
                "campaign_combat_status_view",
                campaign_slug=campaign.slug,
                combatant=selected_combatant_id,
            )
            if can_manage_combat and selected_combatant_id is not None
            else ""
        )

        return {
            "campaign": campaign,
            "combat_system_supported": combat_system_supported,
            "combat_tracker": tracker_view,
            "available_character_choices": available_character_choices,
            "available_statblock_choices": available_statblock_choices,
            "combat_condition_options": combat_condition_options,
            "can_manage_combat": can_manage_combat,
            "can_access_dm_content": can_access_dm_content,
            "can_access_systems": can_access_systems,
            "combat_live_state_token": build_combat_live_state_token(tracker_view),
            "combat_live_revision": combat_live_revision,
            "combat_live_view_token": combat_live_view_token,
            "live_diagnostics_enabled": app.config["LIVE_DIAGNOSTICS"],
            "combat_poll_active_interval_ms": combat_poll_settings["active_interval_ms"],
            "combat_poll_idle_interval_ms": combat_poll_settings["idle_interval_ms"],
            "combat_poll_idle_threshold_ms": combat_poll_settings["idle_threshold_ms"],
            "combat_subpage": combat_subpage,
            "combat_subpages": build_combat_subpages(
                campaign_slug,
                current_subpage=combat_subpage,
                include_character_subpage=bool(accessible_combat_character_rows),
                selected_combatant_id=selected_combatant_id,
                selected_character_combatant_id=selected_character_combatant_id,
                selected_character_slug=selected_character_slug or None,
            ),
            "combat_return_view": "dm" if combat_subpage == "dm" else "combat",
            "show_clear_tracker_in_summary": combat_subpage != "dm",
            "selected_combatant": selected_combatant,
            "selected_combatant_id": selected_combatant_id,
            "requested_combatant_id": requested_combatant_id,
            "combat_tracker_display_combatants": combat_tracker_display_combatants,
            "combat_tracker_section_title": combat_tracker_section_title,
            "combat_tracker_section_meta": combat_tracker_section_meta,
            "dm_focus_combatant_choices": dm_focus_combatant_choices,
            "selected_combatant_source_label": (
                str(selected_combatant.get("source_label") or "").strip()
                if isinstance(selected_combatant, dict)
                else ""
            ),
            "combat_character_entry_url": combat_character_entry_url,
            "selected_combatant_character_url": selected_combatant_character_url,
            "selected_combatant_status_url": selected_combatant_status_url,
            "active_nav": "combat",
            "_combatant_records": combatants,
            "_combat_conditions_by_combatant": conditions_by_combatant,
            "_combat_character_records_by_slug": character_records_by_slug,
            "_selected_combatant_record": selected_combatant_record,
        }

    def build_campaign_combat_character_context(
        campaign_slug: str,
        *,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        context = build_campaign_combat_page_context(
            campaign_slug,
            combat_subpage="character",
            sync_player_character_snapshots=sync_player_character_snapshots,
        )
        campaign = context["campaign"]
        tracker_view = dict(context["combat_tracker"] or {})
        combatants = list(context["_combatant_records"] or [])
        character_records_by_slug = dict(context["_combat_character_records_by_slug"] or {})
        can_manage_combat = bool(context["can_manage_combat"])
        owned_character_slugs = get_owned_character_slugs(campaign_slug)
        allowed_target_rows = list_accessible_combat_character_rows(
            combatants,
            tracker_view,
            character_records_by_slug,
            campaign_slug=campaign_slug,
            can_manage_combat=can_manage_combat,
            owned_character_slugs=owned_character_slugs,
        )
        selected_target = None
        explicit_combatant_id_raw = request.args.get("combatant", "").strip()
        explicit_character_slug = request.args.get("character", "").strip()

        if explicit_combatant_id_raw:
            try:
                explicit_combatant_id = int(explicit_combatant_id_raw)
            except ValueError:
                abort(403)
            selected_target = next(
                (row for row in allowed_target_rows if row["combatant_record"].id == explicit_combatant_id),
                None,
            )
            if selected_target is None:
                abort(403)
        elif explicit_character_slug:
            selected_target = next(
                (
                    row
                    for row in allowed_target_rows
                    if row["record"].definition.character_slug == explicit_character_slug
                ),
                None,
            )
            if selected_target is None:
                abort(403)
        else:
            current_turn_id = next(
                (
                    int(combatant["id"])
                    for combatant in list(tracker_view.get("combatants") or [])
                    if combatant.get("is_current_turn")
                ),
                None,
            )
            if current_turn_id is not None:
                selected_target = next(
                    (
                        row
                        for row in allowed_target_rows
                        if row["combatant_record"].id == current_turn_id
                    ),
                    None,
                )
            if selected_target is None and allowed_target_rows:
                selected_target = allowed_target_rows[0]

        selected_combatant = selected_target["combatant"] if selected_target is not None else None
        selected_record = selected_target["record"] if selected_target is not None else None
        selected_character_slug = (
            selected_record.definition.character_slug if selected_record is not None else None
        )
        selected_combatant_id = (
            selected_target["combatant_record"].id if selected_target is not None else None
        )

        character_detail_context = {}
        if selected_record is not None:
            character_detail_context = build_combat_character_detail_context(
                campaign_slug,
                campaign,
                selected_record,
            )

        accessible_targets = []
        for row in allowed_target_rows:
            record = row["record"]
            combatant = row["combatant"]
            accessible_targets.append(
                {
                    "combatant_id": row["combatant_record"].id,
                    "character_slug": record.definition.character_slug,
                    "name": combatant["name"],
                    "subtitle": combatant["subtitle"],
                    "href": url_for(
                        "campaign_combat_character_view",
                        campaign_slug=campaign.slug,
                        combatant=row["combatant_record"].id,
                    ),
                    "is_active": selected_combatant_id == row["combatant_record"].id,
                }
            )

        context.update(
            {
                "combat_subpages": build_combat_subpages(
                    campaign_slug,
                    current_subpage="character",
                    include_character_subpage=bool(allowed_target_rows),
                    selected_combatant_id=selected_combatant_id,
                    selected_character_combatant_id=selected_combatant_id,
                    selected_character_slug=selected_character_slug,
                ),
                "selected_combatant": selected_combatant,
                "selected_combatant_id": selected_combatant_id,
                "combat_character_targets": accessible_targets,
                "can_edit_combat_character_state": selected_target is not None,
                "combat_character_state_token": build_selected_combatant_state_token(
                    tracker_view,
                    selected_combatant,
                ),
            }
        )
        context.update(character_detail_context)
        return context

    def build_combat_status_source_context(
        campaign_slug: str,
        campaign,
        combatant_record,
        selected_combatant: dict[str, object],
        character_records_by_slug: dict[str, object],
    ) -> dict[str, object]:
        source_kind = str(
            combatant_record.source_kind
            or selected_combatant.get("source_kind")
            or (
                COMBAT_SOURCE_KIND_CHARACTER
                if combatant_record.character_slug
                else COMBAT_SOURCE_KIND_MANUAL_NPC
            )
        ).strip()
        source_context: dict[str, object] = {
            "combat_status_source_mode": source_kind,
            "combat_status_source_label": COMBAT_SOURCE_LABELS.get(source_kind, "Unknown source"),
            "combat_status_source_available": True,
            "combat_status_source_unavailable_message": "",
            "combat_status_statblock": None,
            "combat_status_systems_entry": None,
            "combat_status_character_url": "",
        }

        if source_kind == COMBAT_SOURCE_KIND_CHARACTER:
            record = character_records_by_slug.get(combatant_record.character_slug or "")
            if record is None and combatant_record.character_slug:
                record = get_character_repository().get_visible_character(
                    campaign_slug,
                    combatant_record.character_slug,
                )
            if record is None:
                source_context["combat_status_source_available"] = False
                source_context["combat_status_source_unavailable_message"] = (
                    "The linked character record is no longer available."
                )
                return source_context
            source_context.update(
                build_combat_character_detail_context(
                    campaign_slug,
                    campaign,
                    record,
                )
            )
            return source_context

        if source_kind == COMBAT_SOURCE_KIND_DM_STATBLOCK:
            statblock = None
            try:
                statblock_id = int(combatant_record.source_ref)
            except (TypeError, ValueError):
                statblock_id = None
            if statblock_id is not None:
                statblock = get_campaign_dm_content_service().get_statblock(campaign_slug, statblock_id)
            if statblock is None:
                source_context["combat_status_source_available"] = False
                source_context["combat_status_source_unavailable_message"] = (
                    "The linked DM Content statblock is no longer available."
                )
                return source_context
            source_context["combat_status_statblock"] = {
                "id": statblock.id,
                "title": statblock.title,
                "source_filename": statblock.source_filename,
                "armor_class": statblock.armor_class,
                "max_hp": statblock.max_hp,
                "speed_text": statblock.speed_text,
                "initiative_bonus_label": (
                    f"+{statblock.initiative_bonus}"
                    if statblock.initiative_bonus > 0
                    else str(statblock.initiative_bonus)
                ),
                "body_html": render_campaign_markdown(campaign, statblock.body_markdown),
            }
            return source_context

        if source_kind == COMBAT_SOURCE_KIND_SYSTEMS_MONSTER:
            systems_entry = get_systems_service().get_entry_for_campaign(
                campaign_slug,
                combatant_record.source_ref,
            )
            if systems_entry is None or systems_entry.entry_type != "monster":
                source_context["combat_status_source_available"] = False
                source_context["combat_status_source_unavailable_message"] = (
                    "The linked Systems monster is no longer available to this campaign."
                )
                return source_context
            monster_seed = get_systems_service().build_monster_combat_seed(systems_entry)
            source_context["combat_status_systems_entry"] = {
                "entry_key": systems_entry.entry_key,
                "entry_slug": systems_entry.slug,
                "title": systems_entry.title,
                "source_id": systems_entry.source_id,
                "href": url_for(
                    "campaign_systems_entry_detail",
                    campaign_slug=campaign.slug,
                    entry_slug=systems_entry.slug,
                ),
                "max_hp": monster_seed.max_hp,
                "speed_label": monster_seed.speed_label,
                "initiative_bonus_label": (
                    f"+{monster_seed.initiative_bonus}"
                    if monster_seed.initiative_bonus > 0
                    else str(monster_seed.initiative_bonus)
                ),
                "body_html": str(systems_entry.rendered_html or "").strip(),
            }
            return source_context

        source_context["combat_status_source_available"] = False
        source_context["combat_status_source_unavailable_message"] = (
            "This combatant was added manually, so there is no linked source detail to inspect yet."
        )
        return source_context

    def build_campaign_combat_status_context(
        campaign_slug: str,
        *,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)

        explicit_combatant_id = parse_requested_combatant_id(strict=True)
        context = build_campaign_combat_page_context(
            campaign_slug,
            combat_subpage="status",
            selected_combatant_id=explicit_combatant_id,
            sync_player_character_snapshots=sync_player_character_snapshots,
        )
        campaign = context["campaign"]
        tracker_view = dict(context["combat_tracker"] or {})
        combatants = list(context["_combatant_records"] or [])
        character_records_by_slug = dict(context["_combat_character_records_by_slug"] or {})
        selected_combatant_record, selected_combatant = resolve_selected_tracker_combatant(
            tracker_view,
            combatants,
            explicit_combatant_id=explicit_combatant_id,
            strict_explicit=explicit_combatant_id is not None,
        )
        selected_combatant_id = (
            selected_combatant_record.id if selected_combatant_record is not None else None
        )

        source_context = {}
        if selected_combatant_record is not None and selected_combatant is not None:
            source_context = build_combat_status_source_context(
                campaign_slug,
                campaign,
                selected_combatant_record,
                selected_combatant,
                character_records_by_slug,
            )

        context.update(
            {
                "combat_subpages": build_combat_subpages(
                    campaign_slug,
                    current_subpage="status",
                    include_character_subpage=False,
                    selected_combatant_id=selected_combatant_id,
                    selected_character_combatant_id=(
                        selected_combatant_id
                        if isinstance(selected_combatant, dict)
                        and selected_combatant.get("can_open_character_page")
                        else None
                    ),
                    selected_character_slug=(
                        str(selected_combatant.get("character_slug") or "")
                        if isinstance(selected_combatant, dict)
                        and selected_combatant.get("can_open_character_page")
                        else None
                    ),
                ),
                "selected_combatant": selected_combatant,
                "selected_combatant_id": selected_combatant_id,
                "combat_status_state_token": build_selected_combatant_state_token(
                    tracker_view,
                    selected_combatant,
                ),
            }
        )
        context.update(source_context)
        return context

    def build_campaign_dm_content_page_context(campaign_slug: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        dm_content_service = get_campaign_dm_content_service()
        can_manage_dm_content = can_manage_campaign_dm_content(campaign_slug)
        statblocks = dm_content_service.list_statblocks(campaign_slug)
        custom_conditions = dm_content_service.list_condition_definitions(campaign_slug)

        return {
            "campaign": campaign,
            "dm_content_system_supported": campaign.system == SUPPORTED_COMBAT_SYSTEM,
            "dm_statblocks": statblocks,
            "custom_condition_definitions": custom_conditions,
            "can_manage_dm_content": can_manage_dm_content,
            "active_nav": "dm_content",
        }

    def build_campaign_visibility_control_context(campaign_slug: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        user = get_current_user()
        include_private = bool(user and user.is_admin)
        visibility_rows = []
        for scope in CAMPAIGN_VISIBILITY_SCOPES:
            configured_visibility = get_auth_store().get_campaign_visibility_setting(campaign_slug, scope)
            current_visibility = configured_visibility.visibility if configured_visibility is not None else ""
            effective_visibility = get_effective_campaign_visibility(campaign_slug, scope)
            base_visibility = current_visibility or DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE[scope]
            visibility_rows.append(
                {
                    "scope": scope,
                    "label": CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope],
                    "selected_visibility": base_visibility,
                    "configured_visibility": current_visibility,
                    "configured_visibility_label": VISIBILITY_LABELS.get(current_visibility, "") if current_visibility else "",
                    "effective_visibility": effective_visibility,
                    "effective_visibility_label": VISIBILITY_LABELS[effective_visibility],
                    "choices": list_visibility_choices(include_private=include_private),
                    "is_overridden_by_campaign": scope != "campaign"
                    and effective_visibility != current_visibility
                    and effective_visibility == get_effective_campaign_visibility(campaign_slug, "campaign"),
                }
            )

        return {
            "campaign": campaign,
            "visibility_rows": visibility_rows,
            "can_set_private_visibility": include_private,
            "active_nav": "control",
        }

    def build_campaign_systems_control_context(campaign_slug: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        user = get_current_user()
        include_private = bool(user and user.is_admin)
        systems_service = get_systems_service()
        policy = systems_service.get_campaign_policy(campaign_slug)
        source_rows = []
        for state in systems_service.list_campaign_source_states(campaign_slug):
            entry_count = systems_service.count_entries_for_source(campaign_slug, state.source.source_id)
            choices = []
            for choice in list_visibility_choices(include_private=include_private):
                choices.append(
                    {
                        **choice,
                        "disabled": choice["value"] == "public" and not state.source.public_visibility_allowed,
                    }
                )
            source_rows.append(
                {
                    "source_id": state.source.source_id,
                    "title": state.source.title,
                    "license_class": state.source.license_class,
                    "license_class_label": LICENSE_CLASS_LABELS.get(
                        state.source.license_class,
                        state.source.license_class.replace("_", " ").title(),
                    ),
                    "public_visibility_allowed": state.source.public_visibility_allowed,
                    "requires_unofficial_notice": state.source.requires_unofficial_notice,
                    "is_enabled": state.is_enabled,
                    "selected_visibility": state.default_visibility,
                    "choices": choices,
                    "is_configured": state.is_configured,
                    "entry_count": entry_count,
                }
            )

        return {
            "campaign": campaign,
            "systems_library": policy.library_slug if policy is not None else "",
            "systems_scope_visibility_label": VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "systems")],
            "source_rows": source_rows,
            "has_proprietary_sources": any(row["license_class"] == "proprietary_private" for row in source_rows),
            "proprietary_acknowledged": bool(policy and policy.proprietary_acknowledged_at is not None),
            "can_set_private_visibility": include_private,
            "active_nav": "systems",
        }

    def build_rules_reference_search_result(entry) -> dict[str, object]:
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
        systems_service = get_systems_service()
        entries = systems_service.list_entries_for_campaign_source(
            campaign_slug,
            source_id,
            entry_type=entry_type,
            query=query,
            limit=None,
        )
        return filter_accessible_systems_entries(campaign_slug, entries, limit=limit)

    def build_campaign_systems_index_context(
        campaign_slug: str,
        *,
        query: str = "",
        reference_query: str = "",
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        source_cards = []
        for state in systems_service.list_campaign_source_states(campaign_slug):
            if not state.is_enabled or not can_access_campaign_systems_source(campaign_slug, state.source.source_id):
                continue
            accessible_source_entries = list_accessible_campaign_source_entries(
                campaign_slug,
                state.source.source_id,
                limit=None,
            )
            source_has_rules_reference_entries = bool(
                filter_accessible_systems_entries(
                    campaign_slug,
                    systems_service.list_rules_reference_entries_for_campaign(
                        campaign_slug,
                        include_source_ids=[state.source.source_id],
                        limit=None,
                    ),
                    limit=1,
                )
            )
            source_cards.append(
                {
                    "source_id": state.source.source_id,
                    "title": state.source.title,
                    "license_class_label": LICENSE_CLASS_LABELS.get(
                        state.source.license_class,
                        state.source.license_class.replace("_", " ").title(),
                    ),
                    "entry_count": len(accessible_source_entries),
                    "default_visibility_label": VISIBILITY_LABELS[state.default_visibility],
                    "has_rules_reference_entries": source_has_rules_reference_entries,
                    "rules_reference_search_scope": systems_service.get_rules_reference_search_scope_for_source(
                        state.source
                    ),
                }
            )

        search_query = query.strip()
        rules_reference_query = reference_query.strip()
        include_source_ids = [row["source_id"] for row in source_cards]
        global_rules_reference_source_ids = [
            row["source_id"]
            for row in source_cards
            if row["has_rules_reference_entries"] and row["rules_reference_search_scope"] == "global"
        ]
        source_scoped_rules_reference_sources = [
            {
                "source_id": row["source_id"],
                "title": row["title"],
            }
            for row in source_cards
            if row["has_rules_reference_entries"] and row["rules_reference_search_scope"] == "source_only"
        ]
        search_results = []
        if search_query:
            for entry in filter_accessible_systems_entries(
                campaign_slug,
                systems_service.search_entries_for_campaign(
                    campaign_slug,
                    query=search_query,
                    include_source_ids=include_source_ids,
                    limit=None,
                ),
                limit=250,
            ):
                search_results.append(
                    {
                        "title": entry.title,
                        "entry_type": entry.entry_type,
                        "entry_type_label": SYSTEMS_ENTRY_TYPE_LABELS.get(
                            entry.entry_type,
                            entry.entry_type.replace("_", " ").title(),
                        ),
                        "source_id": entry.source_id,
                        "slug": entry.slug,
                    }
                )
        rules_reference_results = []
        if rules_reference_query:
            for entry in filter_accessible_systems_entries(
                campaign_slug,
                systems_service.search_rules_reference_entries_for_campaign(
                    campaign_slug,
                    query=rules_reference_query,
                    include_source_ids=global_rules_reference_source_ids,
                    limit=None,
                ),
                limit=100,
            ):
                rules_reference_results.append(build_rules_reference_search_result(entry))

        return {
            "campaign": campaign,
            "query": search_query,
            "reference_query": rules_reference_query,
            "source_cards": source_cards,
            "search_results": search_results,
            "rules_reference_results": rules_reference_results,
            "has_rules_reference_search": bool(global_rules_reference_source_ids),
            "source_scoped_rules_reference_sources": source_scoped_rules_reference_sources,
            "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            "active_nav": "systems",
        }

    def build_campaign_systems_source_context(
        campaign_slug: str,
        source_id: str,
        *,
        reference_query: str = "",
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)
        accessible_entries_by_type: dict[str, list[object]] = {}
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
            accessible_entries_by_type[entry_type] = accessible_entries
            all_entry_groups.append(
                {
                    "entry_type": entry_type,
                    "label": SYSTEMS_ENTRY_TYPE_LABELS.get(entry_type, entry_type.replace("_", " ").title()),
                    "count": len(accessible_entries),
                }
            )
        all_entry_groups.sort(key=lambda group: systems_entry_type_sort_key(group["entry_type"]))
        entry_groups = [
            group for group in all_entry_groups if group["entry_type"] not in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        ]
        browsable_entry_count = sum(group["count"] for group in entry_groups)
        hidden_entry_count = sum(
            group["count"] for group in all_entry_groups if group["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        )
        hidden_entry_types = [
            group["entry_type"] for group in all_entry_groups if group["entry_type"] in SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES
        ]
        book_entries = list(accessible_entries_by_type.get("book") or [])
        raw_rules_reference_entries = systems_service.list_rules_reference_entries_for_campaign(
            campaign_slug,
            include_source_ids=[source_id],
            limit=None,
        )
        rules_reference_entries = filter_accessible_systems_entries(
            campaign_slug,
            raw_rules_reference_entries,
            limit=None,
        )
        has_book_rules_reference_entries = any(
            entry.entry_type == "book" for entry in rules_reference_entries
        )
        has_rule_rules_reference_entries = any(
            entry.entry_type == "rule" for entry in rules_reference_entries
        )
        rules_reference_search_scope = systems_service.get_rules_reference_search_scope_for_source(state.source)
        book_visibility_policy_note = (
            systems_service.get_book_entry_policy_note_for_source(state.source)
            if systems_service.count_entries_for_source(campaign_slug, source_id, entry_type="book")
            else ""
        )
        if has_book_rules_reference_entries and has_rule_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's book chapters and rules entries using curated metadata "
                "like chapter labels, section headings, aliases, formulas, and rule facets. "
                "It does not search full entry body text."
            )
        elif has_book_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's book chapters using curated metadata like chapter labels "
                "and section headings. It does not search full entry body text."
            )
        elif has_rule_rules_reference_entries:
            rules_reference_search_meta = (
                "Searches only this source's rules entries using curated metadata like aliases, formulas, "
                "and rule facets. It does not search full entry body text."
            )
        else:
            rules_reference_search_meta = ""
        rules_reference_scope_note = ""
        if (
            rules_reference_entries
            and rules_reference_search_scope == "source_only"
        ):
            rules_reference_scope_note = (
                "This DM-heavy source keeps chapter browse and rules-reference metadata search on this "
                "source page instead of surfacing those chapter matches in the landing-page Rules "
                "Reference Search."
            )
        rules_reference_query = reference_query.strip()
        rules_reference_results = []
        if rules_reference_query:
            for entry in filter_accessible_systems_entries(
                campaign_slug,
                systems_service.search_rules_reference_entries_for_campaign(
                    campaign_slug,
                    query=rules_reference_query,
                    include_source_ids=[source_id],
                    limit=None,
                ),
                limit=100,
            ):
                rules_reference_results.append(build_rules_reference_search_result(entry))
        return {
            "campaign": campaign,
            "source_state": state,
            "entry_groups": entry_groups,
            "book_entries": book_entries,
            "book_visibility_policy_note": book_visibility_policy_note,
            "has_rules_reference_search": bool(rules_reference_entries),
            "rules_reference_search_meta": rules_reference_search_meta,
            "rules_reference_scope_note": rules_reference_scope_note,
            "reference_query": rules_reference_query,
            "rules_reference_results": rules_reference_results,
            "entry_count": sum(group["count"] for group in all_entry_groups),
            "browsable_entry_count": browsable_entry_count,
            "hidden_entry_count": hidden_entry_count,
            "hidden_entry_types": hidden_entry_types,
            "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            "license_class_label": LICENSE_CLASS_LABELS.get(
                state.source.license_class,
                state.source.license_class.replace("_", " ").title(),
            ),
            "active_nav": "systems",
        }

    def build_campaign_systems_source_category_context(
        campaign_slug: str,
        source_id: str,
        entry_type: str,
        *,
        query: str = "",
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)
        normalized_entry_type = (entry_type or "").strip().lower()
        if not normalized_entry_type:
            abort(404)
        entry_count = len(
            list_accessible_campaign_source_entries(
                campaign_slug,
                source_id,
                entry_type=normalized_entry_type,
                limit=None,
            )
        )
        if not entry_count:
            abort(404)
        normalized_query = query.strip()
        entries = list_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            entry_type=normalized_entry_type,
            query=normalized_query,
            limit=None,
        )
        return {
            "campaign": campaign,
            "source_state": state,
            "entry_type": normalized_entry_type,
            "entry_type_label": SYSTEMS_ENTRY_TYPE_LABELS.get(
                normalized_entry_type,
                normalized_entry_type.replace("_", " ").title(),
            ),
            "entries": entries,
            "query": normalized_query,
            "entry_count": entry_count,
            "filtered_entry_count": len(entries),
            "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            "license_class_label": LICENSE_CLASS_LABELS.get(
                state.source.license_class,
                state.source.license_class.replace("_", " ").title(),
            ),
            "active_nav": "systems",
        }

    def build_campaign_systems_entry_context(campaign_slug: str, entry_slug: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        entry = systems_service.get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
        if entry is None:
            abort(404)
        source_state = systems_service.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None or not source_state.is_enabled:
            abort(404)
        book_default_visibility_label = ""
        book_visibility_policy_note = ""
        if entry.entry_type == "book":
            book_default_visibility_label = VISIBILITY_LABELS[
                systems_service.get_default_entry_visibility_for_campaign(campaign_slug, entry)
            ]
            book_visibility_policy_note = systems_service.get_book_entry_policy_note_for_source(source_state.source)
        class_feature_progression_groups = (
            systems_service.build_class_feature_progression_for_class_entry(campaign_slug, entry)
            if entry.entry_type == "class"
            else []
        )
        subclass_feature_progression_groups = (
            systems_service.build_subclass_feature_progression_for_subclass_entry(campaign_slug, entry)
            if entry.entry_type == "subclass"
            else []
        )
        class_optionalfeature_sections = (
            systems_service.build_class_optionalfeature_sections(
                campaign_slug,
                entry,
                class_feature_progression_groups,
            )
            if entry.entry_type == "class"
            else []
        )
        subclass_optionalfeature_sections = (
            systems_service.build_subclass_optionalfeature_sections(
                campaign_slug,
                entry,
                subclass_feature_progression_groups,
            )
            if entry.entry_type == "subclass"
            else []
        )
        class_starting_proficiency_rows = (
            systems_service.build_class_starting_proficiency_rows(campaign_slug, entry)
            if entry.entry_type == "class"
            else []
        )
        feature_detail_card = (
            systems_service.build_feature_detail_card(campaign_slug, entry)
            if entry.entry_type in {"classfeature", "subclassfeature", "optionalfeature"}
            else None
        )
        related_rule_entries = [
            candidate
            for candidate in systems_service.build_related_rules_for_entry(campaign_slug, entry)
            if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
        ]
        related_monster_entries = []
        book_headers = []
        book_section_outline = []
        if entry.entry_type == "book":
            related_monster_entries = [
                candidate
                for candidate in systems_service.build_related_monsters_for_entry(campaign_slug, entry)
                if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
            ]
            book_related_rules_by_anchor = systems_service.build_related_rules_for_book_sections(
                campaign_slug,
                entry,
            )
            book_related_entities_by_anchor = systems_service.build_related_entities_for_book_sections(
                campaign_slug,
                entry,
            )
            raw_headers = (entry.metadata or {}).get("headers")
            if isinstance(raw_headers, list):
                book_headers = [str(item).strip() for item in raw_headers if str(item).strip()]
            raw_outline = (entry.metadata or {}).get("section_outline")
            if isinstance(raw_outline, list):
                for item in raw_outline:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title", "") or "").strip()
                    anchor = str(item.get("anchor", "") or "").strip()
                    if not title or not anchor:
                        continue
                    raw_depth = item.get("depth")
                    depth = int(raw_depth) if isinstance(raw_depth, int) and raw_depth > 0 else 1
                    page = str(item.get("page", "") or "").strip()
                    section_related_rule_entries = [
                        candidate
                        for candidate in book_related_rules_by_anchor.get(anchor, [])
                        if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
                    ]
                    section_related_entity_groups = []
                    for group in book_related_entities_by_anchor.get(anchor, []):
                        if not isinstance(group, dict):
                            continue
                        group_entries = group.get("entries")
                        if not isinstance(group_entries, list):
                            continue
                        accessible_group_entries = [
                            candidate
                            for candidate in group_entries
                            if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
                        ]
                        if not accessible_group_entries:
                            continue
                        section_related_entity_groups.append(
                            {
                                "label": str(group.get("label") or "").strip(),
                                "entries": accessible_group_entries,
                            }
                        )
                    book_section_outline.append(
                        {
                            "title": title,
                            "anchor": anchor,
                            "depth": depth,
                            "page": page,
                            "related_rule_entries": section_related_rule_entries,
                            "related_entity_groups": section_related_entity_groups,
                        }
                    )
        return {
            "campaign": campaign,
            "entry": entry,
            "entry_type_label": SYSTEMS_ENTRY_TYPE_LABELS.get(
                entry.entry_type,
                entry.entry_type.replace("_", " ").title(),
            ),
            "class_starting_proficiency_rows": class_starting_proficiency_rows,
            "class_feature_progression_groups": class_feature_progression_groups,
            "class_optionalfeature_sections": class_optionalfeature_sections,
            "subclass_feature_progression_groups": subclass_feature_progression_groups,
            "subclass_optionalfeature_sections": subclass_optionalfeature_sections,
            "feature_detail_card": feature_detail_card,
            "related_rule_entries": related_rule_entries,
            "related_monster_entries": related_monster_entries,
            "book_headers": book_headers,
            "book_section_outline": book_section_outline,
            "book_default_visibility_label": book_default_visibility_label,
            "book_visibility_policy_note": book_visibility_policy_note,
            "source_state": source_state,
            "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            "license_class_label": LICENSE_CLASS_LABELS.get(
                source_state.source.license_class,
                source_state.source.license_class.replace("_", " ").title(),
            ),
            "active_nav": "systems",
        }

    def build_campaign_session_live_state(
        campaign_slug: str,
        *,
        session_subpage: str = "session",
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        anchor: str | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
    ) -> dict[str, object]:
        normalized_session_subpage = normalize_session_subpage(session_subpage)
        context = build_campaign_session_page_context(
            campaign_slug,
            session_subpage=normalized_session_subpage,
        )
        if live_revision is None:
            live_revision = int(context["session_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["session_live_view_token"] or "")
        payload = {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "active_session_id": context["active_session_id"],
            "manager_state_token": context["session_manager_state_token"],
            "status_html": render_template("_session_status_card.html", **context),
        }
        if normalized_session_subpage == "dm":
            payload.update(
                {
                    "controls_html": render_template("_session_controls_card.html", **context),
                    "staged_articles_html": render_template("_session_staged_articles_card.html", **context),
                    "revealed_articles_html": render_template("_session_revealed_articles_card.html", **context),
                    "logs_html": render_template("_session_logs_card.html", **context),
                }
            )
        else:
            payload.update(
                {
                    "chat_html": render_template("_session_chat_card.html", **context),
                    "composer_html": render_template("_session_composer_card.html", **context),
                }
            )
        if include_flash:
            payload["flash_html"] = render_flash_stack_html()
        if mutation_succeeded is not None:
            payload["ok"] = mutation_succeeded
        if anchor:
            payload["anchor"] = anchor
        return payload

    def build_campaign_combat_live_state(
        campaign_slug: str,
        *,
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        anchor: str | None = None,
        selected_combatant_id: int | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        context = build_campaign_combat_page_context(
            campaign_slug,
            combat_subpage="combat",
            selected_combatant_id=selected_combatant_id,
            sync_player_character_snapshots=sync_player_character_snapshots,
        )
        if live_revision is None:
            live_revision = int(context["combat_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["combat_live_view_token"] or "")
        payload = {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "combat_state_token": context["combat_live_state_token"],
            "summary_html": render_template("_combat_summary_card.html", **context),
            "tracker_html": render_template("_combat_tracker_section.html", **context),
            "context_html": render_template("_combat_context_panel.html", **context),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        if include_flash:
            payload["flash_html"] = render_flash_stack_html()
        if mutation_succeeded is not None:
            payload["ok"] = mutation_succeeded
        if anchor:
            payload["anchor"] = anchor
        return payload

    def build_campaign_combat_dm_live_state(
        campaign_slug: str,
        *,
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        anchor: str | None = None,
        selected_combatant_id: int | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        context = build_campaign_combat_page_context(
            campaign_slug,
            include_control_choices=True,
            combat_subpage="dm",
            selected_combatant_id=selected_combatant_id,
            sync_player_character_snapshots=sync_player_character_snapshots,
        )
        if live_revision is None:
            live_revision = int(context["combat_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["combat_live_view_token"] or "")
        payload = {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "combat_state_token": context["combat_live_state_token"],
            "summary_html": render_template("_combat_summary_card.html", **context),
            "tracker_html": render_template("_combat_tracker_section.html", **context),
            "controls_html": render_template("_combat_dm_controls.html", **context),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        if include_flash:
            payload["flash_html"] = render_flash_stack_html()
        if mutation_succeeded is not None:
            payload["ok"] = mutation_succeeded
        if anchor:
            payload["anchor"] = anchor
        return payload

    def build_campaign_combat_character_live_state(
        campaign_slug: str,
        *,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        context = build_campaign_combat_character_context(
            campaign_slug,
            sync_player_character_snapshots=sync_player_character_snapshots,
        )
        if live_revision is None:
            live_revision = int(context["combat_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["combat_live_view_token"] or "")
        return {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "combat_state_token": context["combat_character_state_token"],
            "snapshot_html": render_template("_combat_character_snapshot.html", **context),
        }

    def build_campaign_combat_status_live_state(
        campaign_slug: str,
        *,
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        context = build_campaign_combat_status_context(
            campaign_slug,
            sync_player_character_snapshots=sync_player_character_snapshots,
        )
        if live_revision is None:
            live_revision = int(context["combat_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["combat_live_view_token"] or "")
        payload = {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "combat_state_token": context["combat_live_state_token"],
            "board_html": render_template("_combat_status_board.html", **context),
            "detail_html": render_template("_combat_status_detail.html", **context),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        if include_flash:
            payload["flash_html"] = render_flash_stack_html()
        if mutation_succeeded is not None:
            payload["ok"] = mutation_succeeded
        return payload

    def respond_to_campaign_session_mutation(
        campaign_slug: str,
        *,
        mutation_succeeded: bool,
        anchor: str | None = None,
        article_mode: str | None = None,
        redirect_to_dm: bool = False,
    ):
        session_subpage = "dm" if redirect_to_dm else "session"
        if is_async_request():
            return jsonify(
                build_campaign_session_live_state(
                    campaign_slug,
                    session_subpage=session_subpage,
                    include_flash=True,
                    mutation_succeeded=mutation_succeeded,
                    anchor=anchor,
                )
            )
        if redirect_to_dm:
            return redirect_to_campaign_session_dm(
                campaign_slug,
                anchor=anchor,
                article_mode=article_mode,
            )
        return redirect_to_campaign_session(
            campaign_slug,
            anchor=anchor,
            article_mode=article_mode,
        )

    def respond_to_campaign_combat_mutation(
        campaign_slug: str,
        *,
        mutation_succeeded: bool,
        anchor: str | None = None,
    ):
        selected_combatant_id = get_requested_combatant_id_from_values()
        combat_return_view = normalize_combat_return_view(request.values.get("combat_view", ""))
        if is_async_request():
            if combat_return_view == "dm":
                return jsonify(
                    build_campaign_combat_dm_live_state(
                        campaign_slug,
                        include_flash=True,
                        mutation_succeeded=mutation_succeeded,
                        anchor=anchor,
                        selected_combatant_id=selected_combatant_id,
                    )
                )
            return jsonify(
                build_campaign_combat_live_state(
                    campaign_slug,
                    include_flash=True,
                    mutation_succeeded=mutation_succeeded,
                    anchor=anchor,
                    selected_combatant_id=selected_combatant_id,
                )
            )
        if combat_return_view == "dm":
            return redirect_to_campaign_combat_dm(
                campaign_slug,
                anchor=anchor,
                combatant_id=selected_combatant_id,
            )
        return redirect_to_campaign_combat(
            campaign_slug,
            anchor=anchor,
            combatant_id=selected_combatant_id,
        )

    def build_session_article_convert_context(
        campaign_slug: str,
        article_id: int,
        *,
        form_data: dict[str, object] | None = None,
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        session_service = get_campaign_session_service()
        article_record = session_service.get_article(campaign_slug, article_id)
        if article_record is None:
            abort(404)

        article_image = session_service.get_article_image(campaign_slug, article_id)
        existing_page = find_published_page_for_session_article(campaign, article_id)
        default_options = build_default_publish_options(campaign, article_record)
        initial_form_data = {
            "title": default_options.title,
            "slug_leaf": default_options.slug_leaf,
            "summary": default_options.summary,
            "section": default_options.section,
            "page_type": default_options.page_type,
            "subsection": default_options.subsection,
            "reveal_after_session": default_options.reveal_after_session,
        }
        if form_data is not None:
            initial_form_data.update(form_data)

        presented_article = present_session_articles(
            campaign,
            [article_record],
            {article_id: article_image} if article_image is not None else {},
            image_url_builder=lambda current_article_id: url_for(
                "campaign_session_article_image",
                campaign_slug=campaign.slug,
                article_id=current_article_id,
            ),
            converted_pages={article_id: existing_page} if existing_page is not None else {},
            page_url_builder=lambda page_slug: url_for(
                "page_view",
                campaign_slug=campaign.slug,
                page_slug=page_slug,
            ),
        )[0]

        return {
            "campaign": campaign,
            "article": presented_article,
            "article_record": article_record,
            "existing_page": existing_page,
            "existing_page_url": (
                url_for("page_view", campaign_slug=campaign.slug, page_slug=existing_page.route_slug)
                if existing_page is not None and campaign.is_page_visible(existing_page)
                else ""
            ),
            "publish_form": initial_form_data,
            "section_choices": list_section_choices(),
            "active_nav": "session",
        }

    @app.context_processor
    def inject_helpers() -> dict[str, object]:
        return {
            "slugify": slugify,
            "app_metadata": build_app_metadata(app.config),
        }

    @app.errorhandler(404)
    def not_found(_: Exception):
        return render_template("not_found.html"), 404

    @app.get("/healthz")
    def health():
        repository = get_repository()
        return jsonify(
            {
                "status": "ok",
                "environment": app.config["APP_ENV"],
                "campaign_count": len(repository.campaigns),
                "app": build_app_metadata(app.config),
                "data": {
                    "db_path": str(app.config["DB_PATH"]),
                    "campaigns_dir": str(app.config["CAMPAIGNS_DIR"]),
                },
                "repository": repository_store.status(),
            }
        )

    @app.get("/")
    def home():
        user = get_current_user()
        if user is None:
            public_entries = get_public_campaign_entries(get_repository())
            if len(public_entries) == 1:
                return redirect(url_for("campaign_view", campaign_slug=public_entries[0].campaign.slug))
            return redirect(url_for("campaign_picker"))

        campaign_entries = get_accessible_campaign_entries(get_repository())
        if len(campaign_entries) == 1:
            return redirect(
                url_for("campaign_view", campaign_slug=campaign_entries[0].campaign.slug)
            )
        return redirect(url_for("campaign_picker"))

    @app.get("/campaigns/<campaign_slug>")
    @campaign_scope_access_required("campaign")
    def campaign_view(campaign_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if not campaign:
            abort(404)

        can_view_wiki = can_access_campaign_scope(campaign_slug, "wiki")
        query = request.args.get("q", "").strip() if can_view_wiki else ""
        grouped_pages: dict[str, list] = {}
        result_count = 0
        if can_view_wiki:
            pages = repository.search_pages(campaign_slug, query)
            grouped_pages_map: dict[str, list] = defaultdict(list)
            for page in pages:
                grouped_pages_map[page.section].append(page)
            grouped_pages = dict(sorted(grouped_pages_map.items(), key=lambda item: section_sort_key(item[0])))
            result_count = len(pages)
            if not query:
                overview_pages = grouped_pages.get("Overview", [])
                if overview_pages:
                    repository.get_page_body_html(campaign_slug, overview_pages[0].route_slug)

        return render_template(
            "campaign.html",
            campaign=campaign,
            grouped_pages=grouped_pages,
            query=query,
            result_count=result_count,
            can_view_wiki=can_view_wiki,
            wiki_visibility_label=VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "wiki")],
            active_nav="wiki",
        )

    @app.get("/campaigns/<campaign_slug>/assets/<path:asset_path>")
    @campaign_scope_access_required("wiki")
    def campaign_asset(campaign_slug: str, asset_path: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if not campaign:
            abort(404)

        asset_file = get_campaign_asset_file(campaign, asset_path)
        if asset_file is None:
            abort(404)

        return send_from_directory(asset_file.parent, asset_file.name)

    @app.get("/campaigns/<campaign_slug>/sections/<section_slug>")
    @campaign_scope_access_required("wiki")
    def section_view(campaign_slug: str, section_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if not campaign:
            abort(404)

        pages = repository.get_section_pages(campaign_slug, section_slug)
        if not pages:
            abort(404)

        top_level_pages = [page for page in pages if not page.subsection]
        subsection_groups: dict[str, list] = defaultdict(list)
        for page in pages:
            if page.subsection:
                subsection_groups[page.subsection].append(page)

        show_subsections = bool(subsection_groups)
        ordered_subsection_groups = [
            (subsection_name, subsection_groups[subsection_name])
            for subsection_name in sorted(
                subsection_groups,
                key=lambda subsection_name: subsection_sort_key(pages[0].section, subsection_name),
            )
        ]

        return render_template(
            "section.html",
            campaign=campaign,
            section_name=pages[0].section,
            pages=pages,
            top_level_pages=top_level_pages,
            subsection_groups=ordered_subsection_groups,
            show_subsections=show_subsections,
            active_nav="wiki",
        )

    @app.get("/campaigns/<campaign_slug>/pages/<path:page_slug>")
    @campaign_scope_access_required("wiki")
    def page_view(campaign_slug: str, page_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if not campaign:
            abort(404)

        page = repository.get_page(campaign_slug, page_slug)
        if not page:
            abort(404)

        backlinks = repository.get_backlinks(campaign_slug, page_slug)
        body_html = repository.get_page_body_html(campaign_slug, page_slug)
        if body_html is None:
            abort(404)
        body_html = body_html.replace(
            "/campaigns/{campaign_slug}/", f"/campaigns/{campaign.slug}/"
        )
        page_image_url = None
        if page.image_path and get_campaign_asset_file(campaign, page.image_path) is not None:
            page_image_url = url_for(
                "campaign_asset",
                campaign_slug=campaign.slug,
                asset_path=page.image_path,
            )

        return render_template(
            "page.html",
            campaign=campaign,
            page=page,
            body_html=body_html,
            page_image_url=page_image_url,
            backlinks=backlinks,
            active_nav="wiki",
        )

    @app.get("/campaigns/<campaign_slug>/control-panel")
    @login_required
    def campaign_control_panel_view(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_visibility(campaign_slug):
            abort(403)

        context = build_campaign_visibility_control_context(campaign_slug)
        return render_template("campaign_control_panel.html", **context)

    @app.post("/campaigns/<campaign_slug>/control-panel/visibility")
    @login_required
    def campaign_control_panel_update_visibility(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_visibility(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        auth_store_instance = get_auth_store()
        changed_scopes: list[str] = []
        for scope in CAMPAIGN_VISIBILITY_SCOPES:
            current_visibility = auth_store_instance.get_campaign_visibility_setting(campaign_slug, scope)
            default_visibility = DEFAULT_CAMPAIGN_VISIBILITY_BY_SCOPE[scope]
            selected_visibility = normalize_visibility_choice(
                request.form.get(
                    f"{scope}_visibility",
                    current_visibility.visibility if current_visibility is not None else default_visibility,
                )
            )
            if not is_valid_visibility(selected_visibility):
                flash(f"Choose a valid visibility for {CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope]}.", "error")
                return render_template(
                    "campaign_control_panel.html",
                    **build_campaign_visibility_control_context(campaign_slug),
                ), 400
            if selected_visibility == VISIBILITY_PRIVATE and not user.is_admin:
                flash("Private visibility is reserved for app admins.", "error")
                return render_template(
                    "campaign_control_panel.html",
                    **build_campaign_visibility_control_context(campaign_slug),
                ), 400

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
                    "source": "campaign_control_panel",
                },
            )
            changed_scopes.append(CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope])

        clear_campaign_visibility_cache(campaign_slug)
        if changed_scopes:
            flash(f"Updated visibility for {', '.join(changed_scopes)}.", "success")
        else:
            flash("Visibility settings already matched those values.", "success")
        return redirect(url_for("campaign_control_panel_view", campaign_slug=campaign_slug))

    @app.get("/campaigns/<campaign_slug>/systems")
    @campaign_scope_access_required("systems")
    def campaign_systems_index(campaign_slug: str):
        query = request.args.get("q", "").strip()
        reference_query = request.args.get("reference_q", "").strip()
        context = build_campaign_systems_index_context(
            campaign_slug,
            query=query,
            reference_query=reference_query,
        )
        return render_template("systems_index.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/search")
    @campaign_scope_access_required("systems")
    def campaign_systems_search(campaign_slug: str):
        query = request.args.get("q", "").strip()
        reference_query = request.args.get("reference_q", "").strip()
        context = build_campaign_systems_index_context(
            campaign_slug,
            query=query,
            reference_query=reference_query,
        )
        return render_template("systems_index.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/sources/<source_id>")
    @campaign_systems_source_access_required
    def campaign_systems_source_detail(campaign_slug: str, source_id: str):
        reference_query = request.args.get("reference_q", "").strip()
        context = build_campaign_systems_source_context(
            campaign_slug,
            source_id,
            reference_query=reference_query,
        )
        return render_template("systems_source_detail.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/sources/<source_id>/types/<entry_type>")
    @campaign_systems_source_access_required
    def campaign_systems_source_type_detail(campaign_slug: str, source_id: str, entry_type: str):
        query = request.args.get("q", "").strip()
        context = build_campaign_systems_source_category_context(
            campaign_slug,
            source_id,
            entry_type,
            query=query,
        )
        return render_template("systems_source_type_detail.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/entries/<entry_slug>")
    @campaign_systems_entry_access_required
    def campaign_systems_entry_detail(campaign_slug: str, entry_slug: str):
        context = build_campaign_systems_entry_context(campaign_slug, entry_slug)
        return render_template("systems_entry_detail.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/control-panel")
    @login_required
    def campaign_systems_control_panel_view(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)
        context = build_campaign_systems_control_context(campaign_slug)
        return render_template("campaign_systems_control_panel.html", **context)

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/sources")
    @login_required
    def campaign_systems_control_panel_update_sources(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        systems_service = get_systems_service()
        source_states = systems_service.list_campaign_source_states(campaign_slug)
        updates = []
        for state in source_states:
            visibility_default = state.default_visibility
            updates.append(
                {
                    "source_id": state.source.source_id,
                    "is_enabled": request.form.get(f"source_{state.source.source_id}_enabled") == "1",
                    "default_visibility": request.form.get(
                        f"source_{state.source.source_id}_visibility",
                        visibility_default,
                    ),
                }
            )

        try:
            changed_sources = systems_service.update_campaign_sources(
                campaign_slug,
                updates=updates,
                actor_user_id=user.id,
                acknowledge_proprietary=request.form.get("acknowledge_proprietary") == "yes",
                can_set_private=bool(user.is_admin),
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return render_template(
                "campaign_systems_control_panel.html",
                **build_campaign_systems_control_context(campaign_slug),
            ), 400

        if changed_sources:
            auth_store_instance = get_auth_store()
            for source in changed_sources:
                state = systems_service.get_campaign_source_state(campaign_slug, source.source_id)
                if state is None:
                    continue
                auth_store_instance.write_audit_event(
                    event_type="campaign_systems_source_updated",
                    actor_user_id=user.id,
                    campaign_slug=campaign_slug,
                    metadata={
                        "library_slug": source.library_slug,
                        "source_id": source.source_id,
                        "visibility": state.default_visibility,
                        "is_enabled": state.is_enabled,
                        "source": "campaign_systems_control_panel",
                    },
                )
            flash(
                f"Updated systems sources: {', '.join(source.source_id for source in changed_sources)}.",
                "success",
            )
        else:
            flash("Systems source settings already matched those values.", "success")

        return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/overrides")
    @login_required
    def campaign_systems_control_panel_update_override(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        raw_enabled_override = normalize_lookup(request.form.get("is_enabled_override", ""))
        enabled_override = None
        if raw_enabled_override == "enabled":
            enabled_override = True
        elif raw_enabled_override == "disabled":
            enabled_override = False

        try:
            override = get_systems_service().update_campaign_entry_override(
                campaign_slug,
                entry_key=request.form.get("entry_key", ""),
                visibility_override=request.form.get("visibility_override", "").strip() or None,
                is_enabled_override=enabled_override,
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return render_template(
                "campaign_systems_control_panel.html",
                **build_campaign_systems_control_context(campaign_slug),
            ), 400

        get_auth_store().write_audit_event(
            event_type="campaign_systems_entry_override_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": override.entry_key,
                "visibility": override.visibility_override or "inherit",
                "source": "campaign_systems_control_panel",
            },
        )
        flash("Saved systems entry override.", "success")
        return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))

    @app.get("/campaigns/<campaign_slug>/dm-content")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_view(campaign_slug: str):
        context = build_campaign_dm_content_page_context(campaign_slug)
        return render_template("dm_content.html", **context)

    @app.post("/campaigns/<campaign_slug>/dm-content/statblocks")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_upload_statblock(campaign_slug: str):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        if campaign.system != SUPPORTED_COMBAT_SYSTEM:
            flash(
                f"Statblock upload is only implemented for {SUPPORTED_COMBAT_SYSTEM} right now.",
                "error",
            )
            return redirect_to_campaign_dm_content(campaign_slug, anchor="dm-content-statblocks")

        user = get_current_user()
        if user is None:
            abort(403)

        markdown_file = request.files.get("statblock_file")
        filename = (markdown_file.filename or "").strip() if markdown_file is not None else ""
        data_blob = markdown_file.read() if markdown_file is not None else b""
        try:
            get_campaign_dm_content_service().create_statblock(
                campaign_slug,
                filename=filename,
                data_blob=data_blob,
                created_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Statblock saved to DM Content.", "success")

        return redirect_to_campaign_dm_content(campaign_slug, anchor="dm-content-statblocks")

    @app.post("/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>/delete")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_delete_statblock(campaign_slug: str, statblock_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        try:
            deleted_statblock = get_campaign_dm_content_service().delete_statblock(campaign_slug, statblock_id)
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
        else:
            flash(f"Deleted {deleted_statblock.title} from DM Content.", "success")

        return redirect_to_campaign_dm_content(campaign_slug, anchor="dm-content-statblocks")

    @app.post("/campaigns/<campaign_slug>/dm-content/conditions")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_add_condition_definition(campaign_slug: str):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            get_campaign_dm_content_service().create_condition_definition(
                campaign_slug,
                name=request.form.get("name", ""),
                description_markdown=request.form.get("description_markdown", ""),
                created_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Custom condition saved to DM Content.", "success")

        return redirect_to_campaign_dm_content(campaign_slug, anchor="dm-content-conditions")

    @app.post("/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>/delete")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_delete_condition_definition(campaign_slug: str, condition_definition_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        try:
            deleted_definition = get_campaign_dm_content_service().delete_condition_definition(
                campaign_slug,
                condition_definition_id,
            )
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
        else:
            flash(f"Deleted custom condition {deleted_definition.name}.", "success")

        return redirect_to_campaign_dm_content(campaign_slug, anchor="dm-content-conditions")

    @app.get("/campaigns/<campaign_slug>/combat")
    @campaign_scope_access_required("combat")
    def campaign_combat_view(campaign_slug: str):
        context = build_campaign_combat_page_context(
            campaign_slug,
            combat_subpage="combat",
        )
        return render_template("combat.html", **context)

    @app.get("/campaigns/<campaign_slug>/combat/live-state")
    @campaign_scope_access_required("combat")
    def campaign_combat_live_state(campaign_slug: str):
        state_check_started_at = time.perf_counter()
        live_metadata = build_combat_live_metadata(campaign_slug, "combat")
        state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
        if should_short_circuit_live_response(
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
        ):
            return build_live_json_response(
                build_unchanged_live_payload(
                    live_revision=int(live_metadata["live_revision"] or 0),
                    live_view_token=str(live_metadata["live_view_token"] or ""),
                ),
                view_name="combat",
                changed=False,
                live_revision=int(live_metadata["live_revision"] or 0),
                state_check_ms=state_check_ms,
                render_ms=0.0,
            )

        render_started_at = time.perf_counter()
        payload = build_campaign_combat_live_state(
            campaign_slug,
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
            sync_player_character_snapshots=False,
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        return build_live_json_response(
            payload,
            view_name="combat",
            changed=True,
            live_revision=int(live_metadata["live_revision"] or 0),
            state_check_ms=state_check_ms,
            render_ms=render_ms,
        )

    @app.get("/campaigns/<campaign_slug>/combat/dm")
    @campaign_scope_access_required("combat")
    def campaign_combat_dm_view(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        context = build_campaign_combat_page_context(
            campaign_slug,
            include_control_choices=True,
            combat_subpage="dm",
        )
        return render_template("combat_dm.html", **context)

    @app.get("/campaigns/<campaign_slug>/combat/dm/live-state")
    @campaign_scope_access_required("combat")
    def campaign_combat_dm_live_state(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        selected_combatant_id = parse_requested_combatant_id()
        state_check_started_at = time.perf_counter()
        live_metadata = build_combat_live_metadata(
            campaign_slug,
            "dm",
            selected_combatant_id=selected_combatant_id,
        )
        state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
        if should_short_circuit_live_response(
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
        ):
            return build_live_json_response(
                build_unchanged_live_payload(
                    live_revision=int(live_metadata["live_revision"] or 0),
                    live_view_token=str(live_metadata["live_view_token"] or ""),
                ),
                view_name="combat-dm",
                changed=False,
                live_revision=int(live_metadata["live_revision"] or 0),
                state_check_ms=state_check_ms,
                render_ms=0.0,
            )

        render_started_at = time.perf_counter()
        payload = build_campaign_combat_dm_live_state(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
            sync_player_character_snapshots=False,
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        return build_live_json_response(
            payload,
            view_name="combat-dm",
            changed=True,
            live_revision=int(live_metadata["live_revision"] or 0),
            state_check_ms=state_check_ms,
            render_ms=render_ms,
        )

    @app.get("/campaigns/<campaign_slug>/combat/status")
    @campaign_scope_access_required("combat")
    def campaign_combat_status_view(campaign_slug: str):
        context = build_campaign_combat_status_context(campaign_slug)
        return render_template("combat_status.html", **context)

    @app.get("/campaigns/<campaign_slug>/combat/status/live-state")
    @campaign_scope_access_required("combat")
    def campaign_combat_status_live_state(campaign_slug: str):
        state_check_started_at = time.perf_counter()
        live_metadata = build_combat_live_metadata(campaign_slug, "status")
        state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
        if should_short_circuit_live_response(
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
        ):
            return build_live_json_response(
                build_unchanged_live_payload(
                    live_revision=int(live_metadata["live_revision"] or 0),
                    live_view_token=str(live_metadata["live_view_token"] or ""),
                ),
                view_name="combat-status",
                changed=False,
                live_revision=int(live_metadata["live_revision"] or 0),
                state_check_ms=state_check_ms,
                render_ms=0.0,
            )

        render_started_at = time.perf_counter()
        payload = build_campaign_combat_status_live_state(
            campaign_slug,
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
            sync_player_character_snapshots=False,
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        return build_live_json_response(
            payload,
            view_name="combat-status",
            changed=True,
            live_revision=int(live_metadata["live_revision"] or 0),
            state_check_ms=state_check_ms,
            render_ms=render_ms,
        )

    @app.get("/campaigns/<campaign_slug>/combat/character")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_view(campaign_slug: str):
        requested_combatant_id = parse_requested_combatant_id()
        if can_manage_campaign_combat(campaign_slug):
            return redirect_to_campaign_combat_status(
                campaign_slug,
                combatant_id=requested_combatant_id,
            )
        context = build_campaign_combat_character_context(campaign_slug)
        return render_template("combat_character.html", **context)

    @app.get("/campaigns/<campaign_slug>/combat/character/live-state")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_live_state(campaign_slug: str):
        state_check_started_at = time.perf_counter()
        live_metadata = build_combat_live_metadata(campaign_slug, "character")
        state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
        if should_short_circuit_live_response(
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
        ):
            return build_live_json_response(
                build_unchanged_live_payload(
                    live_revision=int(live_metadata["live_revision"] or 0),
                    live_view_token=str(live_metadata["live_view_token"] or ""),
                ),
                view_name="combat-character",
                changed=False,
                live_revision=int(live_metadata["live_revision"] or 0),
                state_check_ms=state_check_ms,
                render_ms=0.0,
            )

        render_started_at = time.perf_counter()
        payload = build_campaign_combat_character_live_state(
            campaign_slug,
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
            sync_player_character_snapshots=False,
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        return build_live_json_response(
            payload,
            view_name="combat-character",
            changed=True,
            live_revision=int(live_metadata["live_revision"] or 0),
            state_check_ms=state_check_ms,
            render_ms=render_ms,
        )

    @app.post("/campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/resources/<resource_id>")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_resource(
        campaign_slug: str,
        combatant_id: int,
        resource_id: str,
    ):
        return run_combat_character_mutation(
            campaign_slug,
            combatant_id,
            anchor="combat-character-resources",
            success_message="Resource updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_resource(
                record,
                resource_id,
                expected_revision=expected_revision,
                current=request.form.get("current"),
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/spell-slots/<int:level>")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_spell_slots(
        campaign_slug: str,
        combatant_id: int,
        level: int,
    ):
        return run_combat_character_mutation(
            campaign_slug,
            combatant_id,
            anchor="combat-character-spell-slots",
            success_message="Spell slot usage updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_spell_slots(
                record,
                level,
                slot_lane_id=request.form.get("slot_lane_id", ""),
                expected_revision=expected_revision,
                used=request.form.get("used"),
                delta_used=request.form.get("delta_used"),
                updated_by_user_id=user_id,
            ),
        )

    @app.get("/campaigns/<campaign_slug>/combat/systems-monsters/search")
    @campaign_scope_access_required("combat")
    def campaign_combat_search_systems_monsters(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return jsonify(
                {
                    "results": [],
                    "message": "Combat tracker support for this campaign system is not available yet.",
                }
            )
        if not can_access_campaign_scope(campaign_slug, "systems"):
            abort(403)

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "results": [],
                    "message": "Type at least 2 letters to search the Systems monster list.",
                }
            )

        systems_service = get_systems_service()
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

        if results:
            message = (
                "Showing the first 30 matching monsters."
                if len(results) == 30
                else f"Found {len(results)} matching monster{'s' if len(results) != 1 else ''}."
            )
        else:
            message = "No Systems monsters matched that search."

        return jsonify(
            {
                "results": results,
                "message": message,
            }
        )

    @app.post("/campaigns/<campaign_slug>/combat/player-combatants")
    @campaign_scope_access_required("combat")
    def campaign_combat_add_player(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_player_character(
                campaign_slug,
                character_slug=request.form.get("character_slug", ""),
                turn_value=request.form.get("turn_value"),
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Player character added to the combat tracker.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-tracker",
        )

    @app.post("/campaigns/<campaign_slug>/combat/npc-combatants")
    @campaign_scope_access_required("combat")
    def campaign_combat_add_npc(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_npc_combatant(
                campaign_slug,
                display_name=request.form.get("display_name", ""),
                turn_value=request.form.get("turn_value"),
                current_hp=request.form.get("current_hp"),
                max_hp=request.form.get("max_hp"),
                temp_hp=request.form.get("temp_hp"),
                movement_total=request.form.get("movement_total"),
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("NPC combatant added to the combat tracker.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-tracker",
        )

    @app.post("/campaigns/<campaign_slug>/combat/statblock-combatants")
    @campaign_scope_access_required("combat")
    def campaign_combat_add_statblock_npc(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )
        if not can_access_campaign_scope(campaign_slug, "dm_content"):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        statblock_id_raw = request.form.get("statblock_id", "").strip()
        try:
            statblock_id = int(statblock_id_raw)
        except ValueError:
            flash("Choose a valid DM Content statblock to add.", "error")
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        statblock = get_campaign_dm_content_service().get_statblock(campaign_slug, statblock_id)
        if statblock is None:
            flash("Choose a valid DM Content statblock to add.", "error")
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_npc_combatant(
                campaign_slug,
                display_name=request.form.get("display_name", "").strip() or statblock.title,
                turn_value=request.form.get("turn_value", "").strip() or statblock.initiative_bonus,
                initiative_bonus=statblock.initiative_bonus,
                current_hp=statblock.max_hp,
                max_hp=statblock.max_hp,
                temp_hp=0,
                movement_total=statblock.movement_total,
                source_kind=COMBAT_SOURCE_KIND_DM_STATBLOCK,
                source_ref=str(statblock.id),
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("NPC combatant added from DM Content.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-tracker",
        )

    @app.post("/campaigns/<campaign_slug>/combat/systems-monsters")
    @campaign_scope_access_required("combat")
    def campaign_combat_add_systems_monster(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )
        if not can_access_campaign_scope(campaign_slug, "systems"):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        entry_key = request.form.get("entry_key", "").strip()
        monster_entry = get_systems_service().get_entry_for_campaign(campaign_slug, entry_key)
        if monster_entry is None or monster_entry.entry_type != "monster":
            flash("Choose a valid Systems monster to add.", "error")
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        monster_seed = get_systems_service().build_monster_combat_seed(monster_entry)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_npc_combatant(
                campaign_slug,
                display_name=request.form.get("display_name", "").strip() or monster_entry.title,
                turn_value=request.form.get("turn_value", "").strip() or monster_seed.initiative_bonus,
                initiative_bonus=monster_seed.initiative_bonus,
                current_hp=monster_seed.max_hp,
                max_hp=monster_seed.max_hp,
                temp_hp=0,
                movement_total=monster_seed.movement_total,
                source_kind=COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
                source_ref=monster_entry.entry_key,
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash(f"NPC combatant added from Systems ({monster_entry.source_id}).", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-tracker",
        )

    @app.post("/campaigns/<campaign_slug>/combat/advance-turn")
    @campaign_scope_access_required("combat")
    def campaign_combat_advance_turn(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-summary",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().advance_turn(
                campaign_slug,
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Advanced turn order.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-summary",
        )

    @app.post("/campaigns/<campaign_slug>/combat/clear")
    @campaign_scope_access_required("combat")
    def campaign_combat_clear(campaign_slug: str):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-summary",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().clear_tracker(
                campaign_slug,
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Combat tracker cleared.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-summary",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/set-current")
    @campaign_scope_access_required("combat")
    def campaign_combat_set_current_turn(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().set_current_turn(
                campaign_slug,
                combatant_id,
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Current turn updated.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=f"combatant-{combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/turn")
    @campaign_scope_access_required("combat")
    def campaign_combat_update_turn_value(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor=f"combatant-{combatant_id}",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().update_turn_value(
                campaign_slug,
                combatant_id,
                turn_value=request.form.get("turn_value"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Turn value saved.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=f"combatant-{combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/vitals")
    @campaign_scope_access_required("combat")
    def campaign_combat_update_vitals(campaign_slug: str, combatant_id: int):
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor=f"combatant-{combatant_id}",
            )

        combat_service = get_campaign_combat_service()
        combatant = combat_service.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            abort(404)

        user = get_current_user()
        if user is None:
            abort(403)

        if combatant.is_player_character and combatant.character_slug:
            if not can_manage_campaign_combat(campaign_slug) and combatant.character_slug not in get_owned_character_slugs(
                campaign_slug
            ):
                abort(403)
            mutation_succeeded = False
            try:
                expected_revision = parse_expected_revision()
                combat_service.update_player_character_vitals(
                    campaign_slug,
                    combatant_id,
                    expected_revision=expected_revision,
                    current_hp=request.form.get("current_hp"),
                    temp_hp=request.form.get("temp_hp"),
                    updated_by_user_id=user.id,
                )
            except CharacterStateConflictError:
                flash("This sheet changed in another session. Refresh the page and try again.", "error")
            except (CharacterStateValidationError, CampaignCombatValidationError, ValueError) as exc:
                flash(str(exc), "error")
            else:
                flash("Combat vitals updated.", "success")
                mutation_succeeded = True
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=mutation_succeeded,
                anchor=f"combatant-{combatant_id}",
            )

        if not can_manage_campaign_combat(campaign_slug):
            abort(403)

        mutation_succeeded = False
        try:
            combat_service.update_npc_vitals(
                campaign_slug,
                combatant_id,
                current_hp=request.form.get("current_hp"),
                max_hp=request.form.get("max_hp"),
                temp_hp=request.form.get("temp_hp"),
                movement_total=request.form.get("movement_total"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Combat vitals updated.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=f"combatant-{combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/resources")
    @campaign_scope_access_required("combat")
    def campaign_combat_update_resources(campaign_slug: str, combatant_id: int):
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor=f"combatant-{combatant_id}",
            )

        user = get_current_user()
        if user is None:
            abort(403)
        combat_service = get_campaign_combat_service()
        combatant = combat_service.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            abort(404)
        if combatant.is_player_character and combatant.character_slug:
            if not can_manage_campaign_combat(campaign_slug) and combatant.character_slug not in get_owned_character_slugs(
                campaign_slug
            ):
                abort(403)
        elif not can_manage_campaign_combat(campaign_slug):
            abort(403)

        mutation_succeeded = False
        try:
            combat_service.update_resources(
                campaign_slug,
                combatant_id,
                has_action=request.form.get("has_action") == "1",
                has_bonus_action=request.form.get("has_bonus_action") == "1",
                has_reaction=request.form.get("has_reaction") == "1",
                movement_remaining=request.form.get("movement_remaining"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Combat resources updated.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=f"combatant-{combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/player-detail-visibility")
    @campaign_scope_access_required("combat")
    def campaign_combat_update_player_detail_visibility(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor=f"combatant-{combatant_id}",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().update_player_detail_visibility(
                campaign_slug,
                combatant_id,
                player_detail_visible=request.form.get("player_detail_visible") == "1",
                updated_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Player-facing NPC detail updated.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=f"combatant-{combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/conditions")
    @campaign_scope_access_required("combat")
    def campaign_combat_add_condition(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor=f"combatant-{combatant_id}",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_condition(
                campaign_slug,
                combatant_id,
                name=request.form.get("condition_name", ""),
                duration_text=request.form.get("duration_text", ""),
                created_by_user_id=user.id,
            )
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Condition added.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=f"combatant-{combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/conditions/<int:condition_id>/delete")
    @campaign_scope_access_required("combat")
    def campaign_combat_delete_condition(campaign_slug: str, condition_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        try:
            deleted_condition = get_campaign_combat_service().delete_condition(campaign_slug, condition_id)
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        flash("Condition removed.", "success")
        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=True,
            anchor=f"combatant-{deleted_condition.combatant_id}",
        )

    @app.post("/campaigns/<campaign_slug>/combat/combatants/<int:combatant_id>/delete")
    @campaign_scope_access_required("combat")
    def campaign_combat_delete_combatant(campaign_slug: str, combatant_id: int):
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)
        if require_supported_combat_system(campaign_slug) is None:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="combat-tracker",
            )

        mutation_succeeded = False
        try:
            deleted_combatant = get_campaign_combat_service().delete_combatant(campaign_slug, combatant_id)
        except CampaignCombatValidationError as exc:
            flash(str(exc), "error")
        else:
            flash(f"Removed {deleted_combatant.display_name} from the combat tracker.", "success")
            mutation_succeeded = True

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="combat-tracker",
        )

    @app.get("/campaigns/<campaign_slug>/session")
    @campaign_scope_access_required("session")
    def campaign_session_view(campaign_slug: str):
        context = build_campaign_session_page_context(campaign_slug, session_subpage="session")
        return render_template("session.html", **context)

    @app.get("/campaigns/<campaign_slug>/session/dm")
    @campaign_scope_access_required("session")
    def campaign_session_dm_view(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        context = build_campaign_session_page_context(campaign_slug, session_subpage="dm")
        return render_template("session_dm.html", **context)

    @app.get("/campaigns/<campaign_slug>/session/live-state")
    @campaign_scope_access_required("session")
    def campaign_session_live_state(campaign_slug: str):
        session_subpage = normalize_session_subpage(request.args.get("view", "session"))
        if session_subpage == "dm" and not can_manage_campaign_session(campaign_slug):
            abort(403)
        state_check_started_at = time.perf_counter()
        live_metadata = build_session_live_metadata(campaign_slug, session_subpage)
        state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
        if should_short_circuit_live_response(
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
        ):
            return build_live_json_response(
                build_unchanged_live_payload(
                    live_revision=int(live_metadata["live_revision"] or 0),
                    live_view_token=str(live_metadata["live_view_token"] or ""),
                ),
                view_name="session",
                changed=False,
                live_revision=int(live_metadata["live_revision"] or 0),
                state_check_ms=state_check_ms,
                render_ms=0.0,
            )

        render_started_at = time.perf_counter()
        payload = build_campaign_session_live_state(
            campaign_slug,
            session_subpage=session_subpage,
            live_revision=int(live_metadata["live_revision"] or 0),
            live_view_token=str(live_metadata["live_view_token"] or ""),
        )
        render_ms = (time.perf_counter() - render_started_at) * 1000
        return build_live_json_response(
            payload,
            view_name=f"session-{session_subpage}",
            changed=True,
            live_revision=int(live_metadata["live_revision"] or 0),
            state_check_ms=state_check_ms,
            render_ms=render_ms,
        )

    @app.get("/campaigns/<campaign_slug>/session/article-sources/search")
    @campaign_scope_access_required("session")
    def campaign_session_search_article_sources(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
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
        return jsonify({"results": results, "message": message})

    @app.get("/campaigns/<campaign_slug>/session/wiki-lookup/search")
    @campaign_scope_access_required("session")
    def campaign_session_wiki_lookup_search(campaign_slug: str):
        if not can_player_access_campaign_scope(campaign_slug, "wiki"):
            return jsonify(
                {
                    "results": [],
                    "message": "No player-visible wiki articles are available right now.",
                }
            )

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "results": [],
                    "message": "Type at least 2 letters to search player-visible wiki articles.",
                }
            )

        results = build_player_session_wiki_search_results(campaign_slug, query, limit=30)
        message = (
            "Showing the first 30 matching wiki articles."
            if len(results) == 30
            else (
                f"Found {len(results)} matching article{'s' if len(results) != 1 else ''}."
                if results
                else "No player-visible wiki articles matched that search."
            )
        )
        return jsonify({"results": results, "message": message})

    @app.get("/campaigns/<campaign_slug>/session/wiki-lookup/preview")
    @campaign_scope_access_required("session")
    def campaign_session_wiki_lookup_preview(campaign_slug: str):
        page_ref = request.args.get("page_ref", "").strip()
        if not page_ref:
            return jsonify(
                {
                    "preview_html": render_template(
                        "_session_wiki_lookup_preview.html",
                        lookup_page=None,
                    )
                }
            )

        preview_context = build_player_session_wiki_lookup_preview_context(campaign_slug, page_ref)
        if preview_context is None:
            return (
                jsonify(
                    {
                        "preview_html": render_template(
                            "_session_wiki_lookup_preview.html",
                            lookup_page=None,
                            lookup_unavailable_message="That article is not currently visible to players.",
                        )
                    }
                ),
                404,
            )

        return jsonify(
            {
                "preview_html": render_template(
                    "_session_wiki_lookup_preview.html",
                    **preview_context,
                )
            }
        )

    @app.get("/campaigns/<campaign_slug>/session-article-images/<int:article_id>")
    @campaign_scope_access_required("session")
    def campaign_session_article_image(campaign_slug: str, article_id: int):
        load_campaign_context(campaign_slug)
        session_service = get_campaign_session_service()
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

    @app.post("/campaigns/<campaign_slug>/session/start")
    @campaign_scope_access_required("session")
    def campaign_session_start(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_session_service().begin_session(
                campaign_slug,
                started_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Session started. Players can now use the Session page chat.", "success")
            mutation_succeeded = True

        return respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="session-controls",
            redirect_to_dm=True,
        )

    @app.post("/campaigns/<campaign_slug>/session/messages")
    @campaign_scope_access_required("session")
    def campaign_session_post_message(campaign_slug: str):
        if not can_post_campaign_session_messages(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_session_service().post_message(
                campaign_slug,
                body_text=request.form.get("body", ""),
                author_display_name=user.display_name,
                author_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Message posted.", "success")
            mutation_succeeded = True

        return respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="session-chat-compose",
        )

    @app.post("/campaigns/<campaign_slug>/session/articles")
    @campaign_scope_access_required("session")
    def campaign_session_create_article(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        session_service = get_campaign_session_service()
        article = None
        article_mode = normalize_session_article_form_mode(request.form.get("article_mode", "manual"))
        markdown_file = request.files.get("markdown_file")
        image_file = request.files.get("image_file")
        referenced_image_file = request.files.get("referenced_image_file")
        mutation_succeeded = False
        try:
            if article_mode == "upload":
                markdown_filename = (markdown_file.filename or "").strip() if markdown_file is not None else ""
                markdown_upload = session_service.parse_article_markdown_upload(
                    filename=markdown_filename,
                    data_blob=markdown_file.read() if markdown_file is not None else b"",
                )
                article = session_service.create_article(
                    campaign_slug,
                    title=markdown_upload.title,
                    body_markdown=markdown_upload.body_markdown,
                    created_by_user_id=user.id,
                )
                referenced_image_filename = (
                    (referenced_image_file.filename or "").strip() if referenced_image_file is not None else ""
                )
                if markdown_upload.image_reference and not referenced_image_filename:
                    raise CampaignSessionValidationError(
                        "This markdown file references an image. Upload the referenced image file too."
                    )
                if referenced_image_file is not None and referenced_image_filename:
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=referenced_image_filename,
                        media_type=referenced_image_file.mimetype,
                        data_blob=referenced_image_file.read(),
                        alt_text=markdown_upload.image_alt,
                        caption=markdown_upload.image_caption,
                        updated_by_user_id=user.id,
                    )
            elif article_mode == "wiki":
                campaign = load_campaign_context(campaign_slug)
                source_kind, source_ref = parse_session_article_source_ref(
                    request.form.get("source_ref", "") or request.form.get("wiki_page_ref", "")
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
                                updated_by_user_id=user.id,
                            )
            else:
                article = session_service.create_article(
                    campaign_slug,
                    title=request.form.get("title", ""),
                    body_markdown=request.form.get("body_markdown", ""),
                    created_by_user_id=user.id,
                )
                image_filename = (image_file.filename or "").strip() if image_file is not None else ""
                if image_file is not None and image_filename:
                    session_service.attach_article_image(
                        campaign_slug,
                        article.id,
                        filename=image_filename,
                        media_type=image_file.mimetype,
                        data_blob=image_file.read(),
                        alt_text=request.form.get("image_alt", ""),
                        caption=request.form.get("image_caption", ""),
                        updated_by_user_id=user.id,
                    )
        except CampaignSessionValidationError as exc:
            if article is not None:
                try:
                    session_service.delete_article(campaign_slug, article.id, updated_by_user_id=user.id)
                except CampaignSessionValidationError:
                    pass
            flash(str(exc), "error")
        else:
            if article_mode == "wiki":
                source_kind, _ = parse_session_article_source_ref(
                    request.form.get("source_ref", "") or request.form.get("wiki_page_ref", "")
                )
                if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
                    flash("Systems entry pulled into the session store.", "success")
                else:
                    flash("Published wiki page pulled into the session store.", "success")
            else:
                flash("Session article saved to the session store.", "success")
            mutation_succeeded = True

        return respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="session-article-store",
            article_mode=article_mode,
            redirect_to_dm=True,
        )

    @app.get("/campaigns/<campaign_slug>/session/articles/<int:article_id>/convert")
    @campaign_scope_access_required("session")
    def campaign_session_convert_article_view(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        context = build_session_article_convert_context(campaign_slug, article_id)
        return render_template("session_article_convert.html", **context)

    @app.post("/campaigns/<campaign_slug>/session/articles/<int:article_id>/convert")
    @campaign_scope_access_required("session")
    def campaign_session_convert_article_submit(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        session_service = get_campaign_session_service()
        article = session_service.get_article(campaign_slug, article_id)
        if article is None:
            abort(404)
        article_image = session_service.get_article_image(campaign_slug, article_id)

        form_data = {
            "title": request.form.get("title", ""),
            "slug_leaf": request.form.get("slug_leaf", ""),
            "summary": request.form.get("summary", ""),
            "section": request.form.get("section", ""),
            "page_type": request.form.get("page_type", ""),
            "subsection": request.form.get("subsection", ""),
            "reveal_after_session": request.form.get("reveal_after_session", ""),
        }

        try:
            options = normalize_publish_options(**form_data)
            result = publish_session_article(
                campaign,
                article,
                article_image=article_image,
                options=options,
                page_store=get_campaign_page_store(),
            )
        except SessionArticlePublishError as exc:
            flash(str(exc), "error")
            context = build_session_article_convert_context(
                campaign_slug,
                article_id,
                form_data=form_data,
            )
            return render_template("session_article_convert.html", **context), 400

        repository_store.refresh()
        session_service.bump_live_state_revision(campaign_slug, updated_by_user_id=user.id)
        if options.reveal_after_session <= campaign.current_session:
            flash("Session article converted into published wiki content.", "success")
            return redirect(
                url_for(
                    "page_view",
                    campaign_slug=campaign_slug,
                    page_slug=result.route_slug,
                )
            )

        flash(
            f"Session article converted into published wiki content. It will appear once the campaign reaches session {options.reveal_after_session}.",
            "success",
        )
        return redirect(
            url_for(
                "campaign_session_convert_article_view",
                campaign_slug=campaign_slug,
                article_id=article_id,
            )
        )

    @app.post("/campaigns/<campaign_slug>/session/articles/<int:article_id>/reveal")
    @campaign_scope_access_required("session")
    def campaign_session_reveal_article(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            get_campaign_session_service().reveal_article(
                campaign_slug,
                article_id,
                revealed_by_user_id=user.id,
                author_display_name=user.display_name,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Session article revealed on the player Session page and saved to the chat history.", "success")
            mutation_succeeded = True

        return respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="session-revealed-articles",
            redirect_to_dm=True,
        )

    @app.post("/campaigns/<campaign_slug>/session/articles/<int:article_id>/delete")
    @campaign_scope_access_required("session")
    def campaign_session_delete_article(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            deleted_article = get_campaign_session_service().delete_article(
                campaign_slug,
                article_id,
                updated_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
            return respond_to_campaign_session_mutation(
                campaign_slug,
                mutation_succeeded=False,
                anchor="session-article-store",
                redirect_to_dm=True,
            )

        if deleted_article.is_revealed:
            flash("Session article deleted. Related reveal entries were removed from chat and logs.", "success")
            return respond_to_campaign_session_mutation(
                campaign_slug,
                mutation_succeeded=True,
                anchor="session-revealed-articles",
                redirect_to_dm=True,
            )

        flash("Session article deleted.", "success")
        return respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=True,
            anchor="session-staged-articles",
            redirect_to_dm=True,
        )

    @app.post("/campaigns/<campaign_slug>/session/close")
    @campaign_scope_access_required("session")
    def campaign_session_close(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            closed_session = get_campaign_session_service().close_session(
                campaign_slug,
                ended_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
            return redirect_to_campaign_session_dm(campaign_slug, anchor="session-controls")

        flash("Session closed. The chat contents are now stored as a chat log.", "success")
        return redirect(
            url_for(
                "campaign_session_log_view",
                campaign_slug=campaign_slug,
                session_id=closed_session.id,
            )
        )

    @app.get("/campaigns/<campaign_slug>/session/logs/<int:session_id>")
    @campaign_scope_access_required("session")
    def campaign_session_log_view(campaign_slug: str, session_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        session_record = get_campaign_session_service().get_session_log(campaign_slug, session_id)
        if session_record is None or session_record.is_active:
            abort(404)

        session_service = get_campaign_session_service()
        all_articles = session_service.list_articles(campaign_slug)
        article_images = session_service.list_article_images([article.id for article in all_articles])
        messages = session_service.list_messages(session_record.id)

        return render_template(
            "session_log.html",
            campaign=campaign,
            session_log=present_session_record(session_record, message_count=len(messages)),
            session_messages=present_session_messages(
                campaign,
                messages,
                all_articles,
                article_images,
                image_url_builder=lambda article_id: url_for(
                    "campaign_session_article_image",
                    campaign_slug=campaign.slug,
                    article_id=article_id,
                ),
            ),
            active_nav="session",
        )

    @app.post("/campaigns/<campaign_slug>/session/logs/<int:session_id>/delete")
    @campaign_scope_access_required("session")
    def campaign_session_log_delete(campaign_slug: str, session_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            get_campaign_session_service().delete_session_log(
                campaign_slug,
                session_id,
                updated_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Chat log deleted.", "success")

        return redirect_to_campaign_session_dm(campaign_slug, anchor="session-chat-logs")

    @app.get("/campaigns/<campaign_slug>/characters")
    @campaign_scope_access_required("characters")
    def character_roster_view(campaign_slug: str):
        repository = get_repository()
        campaign = repository.get_campaign(campaign_slug)
        if not campaign:
            abort(404)
        native_character_tools_supported = campaign_supports_native_character_tools(campaign)

        query = request.args.get("q", "").strip()
        character_cards = present_character_roster(
            get_character_repository().list_visible_characters(campaign_slug)
        )
        if query:
            normalized_query = query.lower()
            character_cards = [
                card for card in character_cards if normalized_query in str(card.get("search_text") or "")
            ]

        return render_template(
            "character_roster.html",
            campaign=campaign,
            character_cards=character_cards,
            query=query,
            result_count=len(character_cards),
            can_create_characters=(
                can_manage_campaign_session(campaign_slug) and native_character_tools_supported
            ),
            native_character_tools_supported=native_character_tools_supported,
            active_nav="characters",
        )

    @app.route("/campaigns/<campaign_slug>/characters/new", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_create_view(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        if not campaign_supports_native_character_tools(campaign):
            return redirect_unsupported_native_character_tools(campaign_slug)
        campaign_page_records = list_builder_campaign_page_records(campaign_slug, campaign)
        form_values = dict(request.form if request.method == "POST" else request.args)
        builder_context = build_level_one_builder_context(
            get_systems_service(),
            campaign_slug,
            form_values,
            campaign_page_records=campaign_page_records,
        )
        builder_ready = bool(
            builder_context.get("class_options")
            and builder_context.get("species_options")
            and builder_context.get("background_options")
        )
        if request.method != "POST":
            return render_character_builder_page(campaign_slug, builder_context)

        if not builder_ready:
            flash(
                "The native character builder needs a supported base class plus enabled Systems species and backgrounds first.",
                "error",
            )
            return render_character_builder_page(campaign_slug, builder_context, status_code=400)

        try:
            definition, import_metadata = build_level_one_character_definition(
                campaign_slug,
                builder_context,
                form_values,
            )
        except CharacterBuildError as exc:
            flash(str(exc), "error")
            return render_character_builder_page(campaign_slug, builder_context, status_code=400)

        config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / definition.character_slug
        definition_path = character_dir / "definition.yaml"
        import_path = character_dir / "import.yaml"
        if definition_path.exists() or import_path.exists():
            flash(
                f"A character with slug '{definition.character_slug}' already exists in this campaign.",
                "error",
            )
            return render_character_builder_page(campaign_slug, builder_context, status_code=409)

        write_yaml(definition_path, definition.to_dict())
        write_yaml(import_path, import_metadata.to_dict())
        character_state_store.initialize_state_if_missing(definition, build_initial_state(definition))
        flash(f"{definition.name} created.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=definition.character_slug,
            )
        )

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/level-up", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_level_up_view(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_native_character_tools(campaign):
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
            )
        campaign_page_records = list_builder_campaign_page_records(campaign_slug, campaign)
        readiness = native_level_up_readiness(
            get_systems_service(),
            campaign_slug,
            record.definition,
            campaign_page_records=campaign_page_records,
        )
        if readiness.get("status") == "repairable":
            flash(str(readiness.get("message") or "This imported character needs progression repair first."), "error")
            return redirect(
                url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if readiness.get("status") != "ready":
            flash(str(readiness.get("message") or "This character is not eligible for the current native level-up flow."), "error")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        form_values = dict(request.form if request.method == "POST" else request.args)
        try:
            level_up_context = build_native_level_up_context(
                get_systems_service(),
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
            return render_character_level_up_page(campaign_slug, character_slug, level_up_context)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            definition, import_metadata, hp_gain = build_native_level_up_character_definition(
                campaign_slug,
                record.definition,
                level_up_context,
                form_values,
                current_import_metadata=record.import_metadata,
            )
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                hp_delta=hp_gain,
            )
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_level_up_page(campaign_slug, character_slug, level_up_context, status_code=409)
        except (CharacterBuildError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_level_up_page(campaign_slug, character_slug, level_up_context, status_code=400)

        config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / character_slug
        write_yaml(character_dir / "definition.yaml", definition.to_dict())
        write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        flash(f"{definition.name} advanced to level {int(level_up_context.get('next_level') or 0)}.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_progression_repair_view(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_native_character_tools(campaign):
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
            )
        campaign_page_records = list_builder_campaign_page_records(campaign_slug, campaign)
        readiness = native_level_up_readiness(
            get_systems_service(),
            campaign_slug,
            record.definition,
            campaign_page_records=campaign_page_records,
        )
        if readiness.get("status") == "ready":
            flash("This character is already ready for native level-up.", "success")
            return redirect(
                url_for(
                    "character_level_up_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if readiness.get("status") == "unsupported":
            flash(str(readiness.get("message") or "This character cannot use the current native progression flow."), "error")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        form_values = dict(request.form if request.method == "POST" else request.args)
        repair_context = build_imported_progression_repair_context(
            get_systems_service(),
            campaign_slug,
            record.definition,
            form_values=form_values if request.method == "POST" else None,
            campaign_page_records=campaign_page_records,
        )
        repair_context["state_revision"] = record.state_record.revision

        if request.method != "POST":
            return render_character_progression_repair_page(campaign_slug, character_slug, repair_context)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            definition, import_metadata = apply_imported_progression_repairs(
                campaign_slug,
                record.definition,
                record.import_metadata,
                repair_context,
                form_values,
            )
            post_repair_readiness = native_level_up_readiness(
                get_systems_service(),
                campaign_slug,
                definition,
                campaign_page_records=campaign_page_records,
            )
            merged_state = merge_state_with_definition(definition, record.state_record.state)
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_progression_repair_page(campaign_slug, character_slug, repair_context, status_code=409)
        except (CharacterBuildError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_progression_repair_page(campaign_slug, character_slug, repair_context, status_code=400)

        config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / character_slug
        write_yaml(character_dir / "definition.yaml", definition.to_dict())
        write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        if post_repair_readiness.get("status") == "ready":
            flash(f"{definition.name} is ready for native level-up.", "success")
            return redirect(
                url_for(
                    "character_level_up_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if post_repair_readiness.get("status") == "repairable":
            flash(
                "Progression repair saved, but this character still needs a few more linked details before native level-up.",
                "error",
            )
            return redirect(
                url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        flash(
            str(post_repair_readiness.get("message") or "This character cannot use the current native progression flow."),
            "error",
        )
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/edit", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_edit_view(campaign_slug: str, character_slug: str):
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_native_character_tools(campaign):
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
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
                app.extensions["systems_service"],
                campaign_slug,
                "spell",
            )
        )
        optionalfeature_catalog = {
            str(entry.slug or "").strip(): entry
            for entry in _list_campaign_enabled_entries(
                app.extensions["systems_service"],
                campaign_slug,
                "optionalfeature",
            )
            if str(entry.slug or "").strip()
        }
        form_values = dict(request.form if request.method == "POST" else request.args)
        edit_context = build_native_character_edit_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values if request.method == "POST" else None,
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
        )
        edit_context["state_revision"] = record.state_record.revision

        if request.method != "POST":
            return render_character_edit_page(campaign_slug, character_slug, edit_context)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            definition, import_metadata, inventory_quantity_overrides = apply_native_character_edits(
                campaign_slug,
                record.definition,
                record.import_metadata,
                campaign_page_records=campaign_page_records,
                form_values=form_values,
                optionalfeature_catalog=optionalfeature_catalog,
                spell_catalog=spell_catalog,
                systems_service=app.extensions["systems_service"],
            )
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
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_edit_page(campaign_slug, character_slug, edit_context, status_code=409)
        except (CharacterEditValidationError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_edit_page(campaign_slug, character_slug, edit_context, status_code=400)

        config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / character_slug
        write_yaml(character_dir / "definition.yaml", definition.to_dict())
        write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        flash("Character details updated.", "success")
        return redirect(
            url_for(
                "character_edit_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/retraining", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_retraining_view(campaign_slug: str, character_slug: str):
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_native_character_tools(campaign):
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
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
                app.extensions["systems_service"],
                campaign_slug,
                "spell",
            )
        )
        optionalfeature_catalog = {
            str(entry.slug or "").strip(): entry
            for entry in _list_campaign_enabled_entries(
                app.extensions["systems_service"],
                campaign_slug,
                "optionalfeature",
            )
            if str(entry.slug or "").strip()
        }
        form_values = dict(request.form if request.method == "POST" else request.args)
        retraining_context = build_native_character_retraining_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values if request.method == "POST" else None,
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
        )
        retraining_context["state_revision"] = record.state_record.revision
        if not list(retraining_context.get("feature_rows") or []):
            flash(
                "This character does not currently have any supported structured retraining options.",
                "error",
            )
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        if request.method != "POST":
            return render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
            )

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            expected_revision = parse_expected_revision()
            definition, import_metadata, inventory_quantity_overrides = apply_native_character_retraining(
                campaign_slug,
                record.definition,
                record.import_metadata,
                campaign_page_records=campaign_page_records,
                form_values=form_values,
                optionalfeature_catalog=optionalfeature_catalog,
                spell_catalog=spell_catalog,
                systems_service=app.extensions["systems_service"],
            )
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
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
                status_code=409,
            )
        except (CharacterEditValidationError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
                status_code=400,
            )

        config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / character_slug
        write_yaml(character_dir / "definition.yaml", definition.to_dict())
        write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        flash("Retraining saved.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
                page="features",
            )
        )

    @app.get("/campaigns/<campaign_slug>/characters/<character_slug>")
    @campaign_scope_access_required("characters")
    def character_read_view(campaign_slug: str, character_slug: str):
        return render_character_page(campaign_slug, character_slug)

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment")
    @campaign_scope_access_required("characters")
    def character_controls_assignment(campaign_slug: str, character_slug: str):
        load_character_context(campaign_slug, character_slug)
        actor = get_current_user()
        if actor is None or not actor.is_admin:
            abort(403)

        raw_user_id = request.form.get("user_id", "").strip()
        try:
            target_user_id = int(raw_user_id)
        except ValueError:
            flash("Choose a valid player to assign.", "error")
            return redirect_to_character_controls(campaign_slug, character_slug)

        store = get_auth_store()
        target_user = store.get_user_by_id(target_user_id)
        if target_user is None or not target_user.is_active:
            flash("Choose an active player account to assign.", "error")
            return redirect_to_character_controls(campaign_slug, character_slug)

        membership = store.get_membership(target_user.id, campaign_slug, statuses=("active",))
        if membership is None or membership.role != "player":
            flash("Character owners must have an active player membership in that campaign.", "error")
            return redirect_to_character_controls(campaign_slug, character_slug)

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
                "source": "character_controls",
            },
        )
        flash(f"Assigned {character_slug} to {target_user.email}.", "success")
        return redirect_to_character_controls(campaign_slug, character_slug)

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment/remove")
    @campaign_scope_access_required("characters")
    def character_controls_assignment_remove(campaign_slug: str, character_slug: str):
        load_character_context(campaign_slug, character_slug)
        actor = get_current_user()
        if actor is None or not actor.is_admin:
            abort(403)

        store = get_auth_store()
        assignment = store.get_character_assignment(campaign_slug, character_slug)
        if assignment is None:
            flash("That character does not currently have an assigned player.", "error")
            return redirect_to_character_controls(campaign_slug, character_slug)

        removed_assignment = store.delete_character_assignment(campaign_slug, character_slug)
        if removed_assignment is None:
            flash("That character assignment no longer exists.", "error")
            return redirect_to_character_controls(campaign_slug, character_slug)

        store.write_audit_event(
            event_type="character_assignment_removed",
            actor_user_id=actor.id,
            target_user_id=removed_assignment.user_id,
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            metadata={
                "assignment_type": removed_assignment.assignment_type,
                "source": "character_controls",
            },
        )
        flash(f"Cleared assignment for {character_slug}.", "success")
        return redirect_to_character_controls(campaign_slug, character_slug)

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/controls/delete")
    @campaign_scope_access_required("characters")
    def character_controls_delete(campaign_slug: str, character_slug: str):
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not can_manage_campaign_content(campaign_slug):
            abort(403)

        confirmation = request.form.get("confirm_character_slug", "").strip()
        if confirmation != character_slug:
            flash(f"Type {character_slug} to confirm deletion.", "error")
            return redirect_to_character_controls(campaign_slug, character_slug)

        store = get_auth_store()
        actor = get_current_user()
        previous_assignment = store.get_character_assignment(campaign_slug, character_slug)
        deleted = delete_campaign_character_file(
            app.config["CAMPAIGNS_DIR"],
            campaign_slug,
            character_slug,
            state_store=app.extensions["character_state_store"],
            auth_store=store,
        )
        if deleted is None:
            flash("That character no longer exists.", "error")
            return redirect(url_for("character_roster_view", campaign_slug=campaign.slug))

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
                "source": "character_controls",
            },
        )
        flash(f"Deleted character {record.definition.name}.", "success")
        return redirect(url_for("character_roster_view", campaign_slug=campaign.slug))

    @app.get("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/systems-items/search")
    @campaign_scope_access_required("characters")
    def character_equipment_systems_item_search(campaign_slug: str, character_slug: str):
        load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "results": [],
                    "message": "Type at least 2 letters to search enabled Systems items.",
                }
            )

        results = []
        for entry in get_systems_service().search_entries_for_campaign(
            campaign_slug,
            query=query,
            entry_type="item",
            limit=20,
        ):
            subtitle_parts = [str(entry.source_id or "").strip()]
            weight_label = format_character_systems_item_weight((entry.metadata or {}).get("weight"))
            if weight_label:
                subtitle_parts.append(weight_label)
            subtitle = " - ".join(part for part in subtitle_parts if part)
            select_label = f"{entry.title} - {subtitle}" if subtitle else entry.title
            results.append(
                {
                    "entry_slug": entry.slug,
                    "title": entry.title,
                    "source_id": entry.source_id,
                    "subtitle": subtitle,
                    "select_label": select_label,
                }
            )

        return jsonify(
            {
                "results": results,
                "message": (
                    f"Found {len(results)} matching Systems items."
                    if results
                    else "No enabled Systems items matched that search."
                ),
            }
        )

    @app.get("/campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/spells/search")
    @campaign_scope_access_required("characters")
    def character_spell_search(campaign_slug: str, character_slug: str):
        _, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        spell_catalog, selected_class_rows = load_character_spell_management_support(
            campaign_slug,
            record.definition,
        )
        results, message = search_character_spell_management_options(
            record.definition,
            spell_catalog=spell_catalog,
            selected_class_rows=selected_class_rows,
            query=request.args.get("q", ""),
            kind=request.args.get("kind", ""),
            target_class_row_id=request.args.get("target_class_row_id", ""),
        )
        return jsonify(
            {
                "results": results,
                "message": message,
            }
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/add")
    @campaign_scope_access_required("characters")
    def character_spell_add(campaign_slug: str, character_slug: str):
        def _action(record):
            spell_catalog, selected_class_rows = load_character_spell_management_support(
                campaign_slug,
                record.definition,
            )
            return apply_character_spell_management_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                spell_catalog=spell_catalog,
                selected_class_rows=selected_class_rows,
                systems_service=get_systems_service(),
                operation="add",
                kind=request.form.get("kind", ""),
                selected_value=request.form.get("selected_value", ""),
                target_class_row_id=request.form.get("target_class_row_id", ""),
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-spell-manager",
            success_message="Spell list updated.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/update")
    @campaign_scope_access_required("characters")
    def character_spell_update(campaign_slug: str, character_slug: str):
        def _action(record):
            spell_catalog, selected_class_rows = load_character_spell_management_support(
                campaign_slug,
                record.definition,
            )
            return apply_character_spell_management_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                spell_catalog=spell_catalog,
                selected_class_rows=selected_class_rows,
                systems_service=get_systems_service(),
                operation="update",
                spell_key=request.form.get("spell_key", ""),
                prepared_value=request.form.get("prepared_value", ""),
                target_class_row_id=request.form.get("target_class_row_id", ""),
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-spell-manager",
            success_message="Prepared spell selection updated.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/spellcasting/remove")
    @campaign_scope_access_required("characters")
    def character_spell_remove(campaign_slug: str, character_slug: str):
        def _action(record):
            spell_catalog, selected_class_rows = load_character_spell_management_support(
                campaign_slug,
                record.definition,
            )
            return apply_character_spell_management_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                spell_catalog=spell_catalog,
                selected_class_rows=selected_class_rows,
                systems_service=get_systems_service(),
                operation="remove",
                spell_key=request.form.get("spell_key", ""),
                target_class_row_id=request.form.get("target_class_row_id", ""),
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-spell-manager",
            success_message="Spell list updated.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-systems")
    @campaign_scope_access_required("characters")
    def character_equipment_add_systems(campaign_slug: str, character_slug: str):
        item_catalog = build_character_item_catalog(campaign_slug)
        def _action(record):
            entry_slug = request.form.get("entry_slug", "").strip()
            if not entry_slug:
                raise CharacterEditValidationError("Choose a Systems item to add.")
            entry = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
            if entry is None or str(entry.entry_type or "").strip() != "item":
                raise CharacterEditValidationError("Choose a valid enabled Systems item to add.")
            existing_manual_entries = [
                dict(item)
                for item in list(record.definition.equipment_catalog or [])
                if str(item.get("source_kind") or "").strip() == "manual_edit"
            ]
            if any(str((item.get("systems_ref") or {}).get("slug") or "").strip() == entry.slug for item in existing_manual_entries):
                raise CharacterEditValidationError(
                    "That Systems item is already listed in supplemental equipment. Update the existing row instead."
                )
            return apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                name=entry.title,
                quantity=request.form.get("quantity", "1"),
                weight=format_character_systems_item_weight((entry.metadata or {}).get("weight")),
                notes=request.form.get("notes", ""),
                systems_ref=build_character_systems_ref(entry),
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Systems item added to supplemental equipment.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-manual")
    @campaign_scope_access_required("characters")
    def character_equipment_add_manual(campaign_slug: str, character_slug: str):
        item_catalog = build_character_item_catalog(campaign_slug)
        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Custom item added to supplemental equipment.",
            action=lambda record: apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                name=request.form.get("name", ""),
                quantity=request.form.get("quantity", "1"),
                weight=request.form.get("weight", ""),
                notes=request.form.get("notes", ""),
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/add-campaign-item")
    @campaign_scope_access_required("characters")
    def character_equipment_add_campaign_item(campaign_slug: str, character_slug: str):
        campaign = load_campaign_context(campaign_slug)
        campaign_page_records = list_visible_character_item_page_records(campaign_slug, campaign)
        item_catalog = build_character_item_catalog(campaign_slug)
        def _action(record):
            selected_page_ref = request.form.get("page_ref", "")
            if not str(selected_page_ref or "").strip():
                raise CharacterEditValidationError("Choose a valid item article to add.")
            return apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                campaign_page_records=campaign_page_records,
                name=request.form.get("name", ""),
                quantity=request.form.get("quantity", "1"),
                weight=request.form.get("weight", ""),
                notes=request.form.get("notes", ""),
                page_ref=selected_page_ref,
            )
        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Campaign item added to supplemental equipment.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/update")
    @campaign_scope_access_required("characters")
    def character_equipment_update(campaign_slug: str, character_slug: str, item_id: str):
        campaign = load_campaign_context(campaign_slug)
        all_campaign_page_records = list_visible_character_page_records(campaign_slug, campaign)
        item_catalog = build_character_item_catalog(campaign_slug)
        def _action(record):
            manual_entry = next(
                (
                    dict(item)
                    for item in list(record.definition.equipment_catalog or [])
                    if str(item.get("source_kind") or "").strip() == "manual_edit"
                    and str(item.get("id") or "").strip() == item_id
                ),
                None,
            )
            if manual_entry is None:
                raise CharacterEditValidationError("Choose a valid supplemental equipment entry to update.")
            systems_ref = dict(manual_entry.get("systems_ref") or {})
            include_page_refs = {
                normalize_character_page_ref(manual_entry.get("page_ref"))
            } if normalize_character_page_ref(manual_entry.get("page_ref")) else None
            campaign_page_records = filter_character_page_records(
                all_campaign_page_records,
                section=CHARACTER_ITEMS_SECTION,
                include_page_refs=include_page_refs,
            )
            return apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                campaign_page_records=campaign_page_records,
                target_item_id=item_id,
                name=request.form.get("name", "") if not systems_ref else str(manual_entry.get("name") or ""),
                quantity=request.form.get("quantity", ""),
                weight=request.form.get("weight", "") if not systems_ref else str(manual_entry.get("weight") or ""),
                notes=request.form.get("notes", ""),
                page_ref=request.form.get("page_ref", "") if not systems_ref else "",
                systems_ref=systems_ref or None,
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Supplemental equipment updated.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/state")
    @campaign_scope_access_required("characters")
    def character_equipment_state_update(campaign_slug: str, character_slug: str, item_id: str):
        item_catalog = build_character_item_catalog(campaign_slug)
        def _action(record):
            inventory_by_ref = {
                build_character_inventory_item_ref(item): dict(item)
                for item in list((record.state_record.state or {}).get("inventory") or [])
                if build_character_inventory_item_ref(item)
            }
            if item_id not in inventory_by_ref:
                raise CharacterEditValidationError("Choose a valid equipment entry to update.")

            is_equipped = bool(request.form.get("is_equipped"))
            is_attuned = bool(request.form.get("is_attuned"))
            attunement_payload = dict((record.state_record.state or {}).get("attunement") or {})
            max_attuned_items = int(attunement_payload.get("max_attuned_items") or 3)
            currently_attuned_refs = {
                item_ref
                for item_ref, item in inventory_by_ref.items()
                if item_ref != item_id and bool(item.get("is_attuned", False))
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
                systems_service=get_systems_service(),
                target_item_id=item_id,
                is_equipped=is_equipped,
                is_attuned=is_attuned,
            )
            return (
                definition,
                import_metadata,
                {},
                {
                    item_id: {
                        "is_equipped": is_equipped,
                        "is_attuned": is_attuned,
                    }
                },
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-equipment-state",
            success_message="Equipment state updated.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/remove")
    @campaign_scope_access_required("characters")
    def character_equipment_remove(campaign_slug: str, character_slug: str, item_id: str):
        item_catalog = build_character_item_catalog(campaign_slug)
        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Supplemental equipment removed.",
            action=lambda record: apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                remove_item_id=item_id,
            ),
        )

    @app.get("/campaigns/<campaign_slug>/characters/<character_slug>/portrait")
    @campaign_scope_access_required("characters")
    def character_portrait_asset(campaign_slug: str, character_slug: str):
        campaign, record = load_character_context(campaign_slug, character_slug)
        portrait = build_character_portrait_context(campaign, record.definition)
        if portrait is None:
            abort(404)
        asset_file = get_campaign_asset_file(campaign, portrait["asset_ref"])
        if asset_file is None:
            abort(404)
        media_type, _ = mimetypes.guess_type(asset_file.name)
        return send_file(
            BytesIO(asset_file.read_bytes()),
            mimetype=media_type,
            download_name=asset_file.name,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait")
    @campaign_scope_access_required("characters")
    def character_personal_portrait(campaign_slug: str, character_slug: str):
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        portrait_upload = request.files.get("portrait_file")
        try:
            expected_revision = parse_expected_revision()
            filename, data_blob = validate_character_portrait_upload(portrait_upload)
            alt_text = request.form.get("portrait_alt", "").strip()
            caption = request.form.get("portrait_caption", "").strip()
            if len(alt_text) > CHARACTER_PORTRAIT_ALT_MAX_LENGTH:
                raise ValueError(
                    f"Portrait alt text must stay under {CHARACTER_PORTRAIT_ALT_MAX_LENGTH} characters."
                )
            if len(caption) > CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH:
                raise ValueError(
                    f"Portrait captions must stay under {CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH} characters."
                )

            existing_asset_ref = str((record.definition.profile or {}).get("portrait_asset_ref") or "").strip()
            next_asset_ref = build_character_portrait_asset_ref(character_slug, filename)
            definition = update_character_portrait_profile(
                record.definition,
                asset_ref=next_asset_ref,
                alt_text=alt_text,
                caption=caption,
            )
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = merge_state_with_definition(definition, record.state_record.state)
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
            write_campaign_asset_file(campaign, next_asset_ref, data_blob=data_blob)
            if existing_asset_ref and existing_asset_ref != next_asset_ref:
                delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash("Portrait saved.", "success")

        return redirect_to_character_mode(campaign_slug, character_slug, anchor="character-personal-portrait")

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/personal/portrait/remove")
    @campaign_scope_access_required("characters")
    def character_personal_portrait_remove(campaign_slug: str, character_slug: str):
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        existing_asset_ref = str((record.definition.profile or {}).get("portrait_asset_ref") or "").strip()
        if not existing_asset_ref:
            flash("That character does not currently have a portrait.", "error")
            return redirect_to_character_mode(campaign_slug, character_slug, anchor="character-personal-portrait")

        try:
            expected_revision = parse_expected_revision()
            definition = update_character_portrait_profile(record.definition)
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            merged_state = merge_state_with_definition(definition, record.state_record.state)
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
            delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash("Portrait removed.", "success")

        return redirect_to_character_mode(campaign_slug, character_slug, anchor="character-personal-portrait")

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/vitals")
    @campaign_scope_access_required("characters")
    def character_session_vitals(campaign_slug: str, character_slug: str):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-vitals",
            success_message="Vitals updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_vitals(
                record,
                expected_revision=expected_revision,
                current_hp=request.form.get("current_hp"),
                temp_hp=request.form.get("temp_hp"),
                hp_delta=request.form.get("hp_delta"),
                temp_hp_delta=request.form.get("temp_hp_delta"),
                clear_temp_hp=request.form.get("clear_temp_hp") == "1",
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/resources/<resource_id>")
    @campaign_scope_access_required("characters")
    def character_session_resource(
        campaign_slug: str,
        character_slug: str,
        resource_id: str,
    ):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-resources",
            success_message="Resource updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_resource(
                record,
                resource_id,
                expected_revision=expected_revision,
                current=request.form.get("current"),
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/spell-slots/<int:level>")
    @campaign_scope_access_required("characters")
    def character_session_spell_slots(
        campaign_slug: str,
        character_slug: str,
        level: int,
    ):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-spell-slots",
            success_message="Spell slot usage updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_spell_slots(
                record,
                level,
                slot_lane_id=request.form.get("slot_lane_id", ""),
                expected_revision=expected_revision,
                used=request.form.get("used"),
                delta_used=request.form.get("delta_used"),
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>")
    @campaign_scope_access_required("characters")
    def character_session_inventory(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-inventory",
            success_message="Inventory updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_inventory_quantity(
                record,
                item_id,
                expected_revision=expected_revision,
                quantity=request.form.get("quantity"),
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/currency")
    @campaign_scope_access_required("characters")
    def character_session_currency(campaign_slug: str, character_slug: str):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-currency",
            success_message="Currency updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_currency(
                record,
                expected_revision=expected_revision,
                values={key: request.form.get(key) for key in ("cp", "sp", "ep", "gp", "pp")},
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/notes")
    @campaign_scope_access_required("characters")
    def character_session_notes(campaign_slug: str, character_slug: str):
        _, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        notes_markdown = request.form.get("player_notes_markdown", "")
        return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
        try:
            expected_revision = parse_expected_revision()
            get_character_state_service().update_player_notes(
                record,
                expected_revision=expected_revision,
                notes_markdown=notes_markdown,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_page(
                campaign_slug,
                character_slug,
                notes_draft=notes_markdown,
                force_session_mode=return_to_session_mode,
                status_code=409,
            )
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_page(
                campaign_slug,
                character_slug,
                notes_draft=notes_markdown,
                force_session_mode=return_to_session_mode,
                status_code=400,
            )

        flash("Note saved.", "success")
        return redirect_to_character_mode(campaign_slug, character_slug, anchor="session-notes")

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/personal")
    @campaign_scope_access_required("characters")
    def character_session_personal(campaign_slug: str, character_slug: str):
        _, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        physical_description_markdown = request.form.get("physical_description_markdown", "")
        background_markdown = request.form.get("background_markdown", "")
        return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
        try:
            expected_revision = parse_expected_revision()
            get_character_state_service().update_personal_details(
                record,
                expected_revision=expected_revision,
                physical_description_markdown=physical_description_markdown,
                background_markdown=background_markdown,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_page(
                campaign_slug,
                character_slug,
                physical_description_draft=physical_description_markdown,
                background_draft=background_markdown,
                force_session_mode=return_to_session_mode,
                status_code=409,
            )
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_page(
                campaign_slug,
                character_slug,
                physical_description_draft=physical_description_markdown,
                background_draft=background_markdown,
                force_session_mode=return_to_session_mode,
                status_code=400,
            )

        flash("Personal details saved.", "success")
        return redirect_to_character_mode(campaign_slug, character_slug, anchor="session-personal")

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/rest/<rest_type>")
    @campaign_scope_access_required("characters")
    def character_session_rest(campaign_slug: str, character_slug: str, rest_type: str):
        if request.form.get("confirm_rest", "") != "1":
            return redirect_to_character_mode(campaign_slug, character_slug, anchor="session-rest")

        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-rest",
            success_message=f"{rest_type.strip().title()} rest applied.",
            action=lambda record, expected_revision, user_id: get_character_state_service().apply_rest(
                record,
                rest_type,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    return app
