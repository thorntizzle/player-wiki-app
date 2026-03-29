from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import mimetypes
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .admin import register_admin
from .api import register_api
from .auth import (
    can_access_campaign_scope,
    can_access_campaign_systems_entry,
    can_access_campaign_systems_source,
    can_manage_campaign_combat,
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
    get_effective_campaign_visibility,
    get_public_campaign_entries,
    has_session_mode_access,
    login_required,
    register_auth,
    role_satisfies_visibility,
)
from .character_builder import (
    CharacterBuildError,
    build_native_level_up_context,
    build_native_level_up_character_definition,
    build_level_one_builder_context,
    build_level_one_character_definition,
    supports_native_level_up,
)
from .character_editor import (
    CharacterEditValidationError,
    apply_native_character_edits,
    build_native_character_edit_context,
)
from .character_importer import write_yaml
from .character_service import CharacterStateValidationError, build_initial_state, merge_state_with_definition
from .combat_presenter import DND_5E_CONDITION_OPTIONS, present_combat_tracker
from .character_presenter import present_character_detail, present_character_roster
from .auth_store import AuthStore
from .campaign_combat_service import CampaignCombatService, CampaignCombatValidationError
from .campaign_combat_store import CampaignCombatStore
from .campaign_dm_content_service import CampaignDMContentService, CampaignDMContentValidationError
from .campaign_dm_content_store import CampaignDMContentStore
from .campaign_page_store import CampaignPageStore
from .campaign_session_service import CampaignSessionService, CampaignSessionValidationError
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
from .db import register_db
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
    "features": "Features",
    "equipment": "Equipment",
    "personal": "Personal",
    "notes": "Notes",
}
SUPPORTED_COMBAT_SYSTEM = "DND-5E"
SYSTEMS_ENTRY_TYPE_LABELS = {
    "action": "Actions",
    "background": "Backgrounds",
    "class": "Classes",
    "classfeature": "Class Features",
    "condition": "Conditions",
    "disease": "Diseases",
    "feat": "Feats",
    "item": "Items",
    "monster": "Monsters",
    "optionalfeature": "Optional Features",
    "race": "Races",
    "sense": "Senses",
    "skill": "Skills",
    "spell": "Spells",
    "status": "Statuses",
    "subclass": "Subclasses",
    "subclassfeature": "Subclass Features",
    "variantrule": "Variant Rules",
}
SYSTEMS_ENTRY_TYPE_ORDER = (
    "class",
    "subclass",
    "classfeature",
    "subclassfeature",
    "spell",
    "feat",
    "optionalfeature",
    "item",
    "race",
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


def normalize_character_read_subpage(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in CHARACTER_READ_SUBPAGE_LABELS:
        return normalized
    return "quick"


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

    def get_repository() -> Repository:
        return repository_store.get()

    def get_campaign_page_store() -> CampaignPageStore:
        return campaign_page_store

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

    def redirect_to_character_mode(campaign_slug: str, character_slug: str, *, anchor: str | None = None):
        read_subpage = normalize_character_read_subpage(request.values.get("page", ""))
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
    ):
        return redirect(
            url_for(
                "campaign_combat_view",
                campaign_slug=campaign_slug,
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

    def require_supported_combat_system(campaign_slug: str):
        campaign = load_campaign_context(campaign_slug)
        if campaign.system != SUPPORTED_COMBAT_SYSTEM:
            flash(
                f"Combat tracker support for {campaign.system or 'this system'} is not available yet.",
                "error",
            )
            return None
        return campaign

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
        can_use_session_mode = has_session_mode_access(campaign_slug, character_slug)
        can_level_up = can_manage_campaign_session(campaign_slug) and supports_native_level_up(record.definition)
        character_subpage = normalize_character_read_subpage(request.args.get("page", ""))
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
            for slug, label in CHARACTER_READ_SUBPAGE_LABELS.items()
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
                can_level_up=can_level_up,
                is_session_mode=is_session_mode,
                rest_preview=rest_preview,
            ),
            status_code,
        )

    def render_character_builder_page(
        campaign_slug: str,
        builder_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign = load_campaign_context(campaign_slug)
        builder_ready = bool(
            builder_context.get("class_options")
            and builder_context.get("species_options")
            and builder_context.get("background_options")
        )
        template_name = (
            "_character_create_builder.html"
            if request.method == "GET" and request.args.get("_live_preview") == "1"
            else "character_create.html"
        )
        return (
            render_template(
                template_name,
                campaign=campaign,
                builder=builder_context,
                builder_ready=builder_ready,
                active_nav="characters",
            ),
            status_code,
        )

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

    def render_character_level_up_page(
        campaign_slug: str,
        character_slug: str,
        level_up_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign = load_campaign_context(campaign_slug)
        template_name = (
            "_character_level_up_builder.html"
            if request.method == "GET" and request.args.get("_live_preview") == "1"
            else "character_level_up.html"
        )
        return (
            render_template(
                template_name,
                campaign=campaign,
                character_slug=character_slug,
                level_up=level_up_context,
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
            "session_subpage": session_subpage,
            "active_nav": "session",
        }

    def build_campaign_combat_page_context(
        campaign_slug: str,
        *,
        include_sidebar_choices: bool = True,
    ) -> dict[str, object]:
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

        if combat_system_supported:
            combat_service = get_campaign_combat_service()
            dm_content_service = get_campaign_dm_content_service()
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
                        "subtitle": str(record.definition.profile.get("class_level_text") or "Character").strip(),
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
            "active_nav": "combat",
        }

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

    def build_campaign_systems_index_context(campaign_slug: str, *, query: str = "") -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        source_cards = []
        for state in systems_service.list_campaign_source_states(campaign_slug):
            if not state.is_enabled or not can_access_campaign_systems_source(campaign_slug, state.source.source_id):
                continue
            source_cards.append(
                {
                    "source_id": state.source.source_id,
                    "title": state.source.title,
                    "license_class_label": LICENSE_CLASS_LABELS.get(
                        state.source.license_class,
                        state.source.license_class.replace("_", " ").title(),
                    ),
                    "entry_count": systems_service.count_entries_for_source(campaign_slug, state.source.source_id),
                    "default_visibility_label": VISIBILITY_LABELS[state.default_visibility],
                }
            )

        search_query = query.strip()
        search_results = []
        if search_query:
            include_source_ids = [row["source_id"] for row in source_cards]
            for entry in systems_service.search_entries_for_campaign(
                campaign_slug,
                query=search_query,
                include_source_ids=include_source_ids,
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

        return {
            "campaign": campaign,
            "query": search_query,
            "source_cards": source_cards,
            "search_results": search_results,
            "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            "active_nav": "systems",
        }

    def build_campaign_systems_source_context(campaign_slug: str, source_id: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        state = systems_service.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            abort(404)
        all_entry_groups = []
        for entry_type, count in systems_service.list_entry_type_counts_for_campaign_source(campaign_slug, source_id):
            all_entry_groups.append(
                {
                    "entry_type": entry_type,
                    "label": SYSTEMS_ENTRY_TYPE_LABELS.get(entry_type, entry_type.replace("_", " ").title()),
                    "count": count,
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
        return {
            "campaign": campaign,
            "source_state": state,
            "entry_groups": entry_groups,
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
        entry_count = systems_service.count_entries_for_source(
            campaign_slug,
            source_id,
            entry_type=normalized_entry_type,
        )
        if not entry_count:
            abort(404)
        normalized_query = query.strip()
        entries = (
            systems_service.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type=normalized_entry_type,
                query=normalized_query,
                limit=None,
            )
            if normalized_query
            else systems_service.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type=normalized_entry_type,
                limit=None,
            )
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
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        anchor: str | None = None,
    ) -> dict[str, object]:
        context = build_campaign_session_page_context(campaign_slug)
        payload = {
            "active_session_id": context["active_session_id"],
            "manager_state_token": context["session_manager_state_token"],
            "status_html": render_template("_session_status_card.html", **context),
            "chat_html": render_template("_session_chat_card.html", **context),
            "composer_html": render_template("_session_composer_card.html", **context),
            "controls_html": render_template("_session_controls_card.html", **context),
            "staged_articles_html": render_template("_session_staged_articles_card.html", **context),
            "revealed_articles_html": render_template("_session_revealed_articles_card.html", **context),
            "logs_html": render_template("_session_logs_card.html", **context),
        }
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
        include_sidebar: bool = True,
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        anchor: str | None = None,
    ) -> dict[str, object]:
        context = build_campaign_combat_page_context(
            campaign_slug,
            include_sidebar_choices=include_sidebar,
        )
        payload = {
            "combat_state_token": context["combat_live_state_token"],
            "summary_html": render_template("_combat_summary_card.html", **context),
            "tracker_html": render_template("_combat_tracker_section.html", **context),
        }
        if include_sidebar:
            payload["sidebar_html"] = render_template("_combat_sidebar.html", **context)
        if include_flash:
            payload["flash_html"] = render_flash_stack_html()
        if mutation_succeeded is not None:
            payload["ok"] = mutation_succeeded
        if anchor:
            payload["anchor"] = anchor
        return payload

    def respond_to_campaign_session_mutation(
        campaign_slug: str,
        *,
        mutation_succeeded: bool,
        anchor: str | None = None,
        article_mode: str | None = None,
        redirect_to_dm: bool = False,
    ):
        if is_async_request():
            return jsonify(
                build_campaign_session_live_state(
                    campaign_slug,
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
        if is_async_request():
            return jsonify(
                build_campaign_combat_live_state(
                    campaign_slug,
                    include_flash=True,
                    mutation_succeeded=mutation_succeeded,
                    anchor=anchor,
                )
            )
        return redirect_to_campaign_combat(campaign_slug, anchor=anchor)

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
        context = build_campaign_systems_index_context(campaign_slug, query=query)
        return render_template("systems_index.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/search")
    @campaign_scope_access_required("systems")
    def campaign_systems_search(campaign_slug: str):
        query = request.args.get("q", "").strip()
        context = build_campaign_systems_index_context(campaign_slug, query=query)
        return render_template("systems_index.html", **context)

    @app.get("/campaigns/<campaign_slug>/systems/sources/<source_id>")
    @campaign_systems_source_access_required
    def campaign_systems_source_detail(campaign_slug: str, source_id: str):
        context = build_campaign_systems_source_context(campaign_slug, source_id)
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
        context = build_campaign_combat_page_context(campaign_slug)
        return render_template("combat.html", **context)

    @app.get("/campaigns/<campaign_slug>/combat/live-state")
    @campaign_scope_access_required("combat")
    def campaign_combat_live_state(campaign_slug: str):
        return jsonify(build_campaign_combat_live_state(campaign_slug, include_sidebar=False))

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
            get_campaign_combat_service().update_resources(
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
        return jsonify(build_campaign_session_live_state(campaign_slug))

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
            flash("Session started. The chat window is now live.", "success")
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
                    )
        except CampaignSessionValidationError as exc:
            if article is not None:
                try:
                    session_service.delete_article(campaign_slug, article.id)
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
            flash("Session article revealed in the chat window.", "success")
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

        try:
            deleted_article = get_campaign_session_service().delete_article(campaign_slug, article_id)
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

        try:
            get_campaign_session_service().delete_session_log(campaign_slug, session_id)
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
            can_create_characters=can_manage_campaign_session(campaign_slug),
            active_nav="characters",
        )

    @app.route("/campaigns/<campaign_slug>/characters/new", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_create_view(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        form_values = dict(request.form if request.method == "POST" else request.args)
        builder_context = build_level_one_builder_context(
            get_systems_service(),
            campaign_slug,
            form_values,
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
        del campaign
        if not supports_native_level_up(record.definition):
            flash("This character is not eligible for the current native level-up flow.", "error")
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

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/edit", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_edit_view(campaign_slug: str, character_slug: str):
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        _, record = load_character_context(campaign_slug, character_slug)
        form_values = dict(request.form if request.method == "POST" else request.args)
        edit_context = build_native_character_edit_context(
            record.definition,
            form_values=form_values if request.method == "POST" else None,
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
                form_values,
            )
            merged_state = merge_state_with_definition(
                definition,
                record.state_record.state,
                inventory_quantity_overrides=inventory_quantity_overrides,
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

    @app.get("/campaigns/<campaign_slug>/characters/<character_slug>")
    @campaign_scope_access_required("characters")
    def character_read_view(campaign_slug: str, character_slug: str):
        return render_character_page(campaign_slug, character_slug)

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
