from __future__ import annotations

from collections import OrderedDict, defaultdict
from html import unescape
import hashlib
import json
import logging
from pathlib import Path
import re
import secrets
import time
from threading import Lock

from flask import Flask, abort, flash, g, jsonify, make_response, redirect, render_template, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge
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
    campaign_scope_access_required,
    clear_campaign_visibility_cache,
    get_accessible_campaign_entries,
    get_auth_store,
    get_campaign_default_scope_visibility,
    get_campaign_role,
    get_current_theme,
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
    _normalize_equipment_payloads,
    _build_spell_catalog,
    _list_campaign_enabled_entries,
    CharacterBuildError,
    apply_imported_progression_repairs,
    build_native_level_up_context,
    build_native_level_up_character_definition,
    build_imported_progression_repair_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    normalize_definition_to_native_model,
    native_level_up_readiness,
    resolve_weapon_wield_mode,
    supports_native_level_up,
    weapon_wield_mode_label,
)
from .character_assets import (
    build_character_item_catalog as build_shared_character_item_catalog,
    build_character_portrait_asset_ref,
    character_portrait_profile,
    prepare_character_portrait_file,
    update_character_portrait_profile,
    validate_character_portrait_text,
)
from .character_editor import (
    CharacterEditValidationError,
    apply_character_spell_management_edit,
    apply_equipment_catalog_edit,
    apply_native_character_retraining,
    build_character_spell_management_context,
    apply_native_character_edits,
    build_linked_feature_authoring_support,
    build_managed_character_import_metadata,
    build_native_character_edit_context,
    build_native_character_retraining_context,
    search_character_spell_management_options,
)
from .character_importer import write_yaml
from .character_equipment_state import (
    build_equipment_state_update_result as build_shared_equipment_state_update_result,
    build_record_equipment_support_lookup,
)
from .character_workspace_sections import (
    SESSION_CHARACTER_SECTION_LABELS,
    build_combat_character_workspace_sections,
    build_session_character_sections,
)
from .character_page_records import (
    list_builder_campaign_page_records as list_builder_campaign_page_records_for_store,
    list_visible_character_page_records as list_visible_character_page_records_for_store,
)
from .character_profile import ensure_profile_class_rows, profile_class_level_text, profile_class_rows, profile_primary_class_ref
from .character_service import CharacterStateValidationError, build_initial_state, merge_state_with_definition
from .loading_presenter import select_campaign_loading_image_urls
from .login_throttle import LoginThrottle
from .runtime_security import sanitize_request_path, validate_production_secret
from .runtime_health import liveness_payload, readiness_payload
from .help_presenter import (
    COMBAT_AND_SESSION_COMBAT_SCOPE,
    COMBAT_AND_SESSION_SESSION_SCOPE,
    build_campaign_help_context as build_shared_campaign_help_context,
)
from .input_limits import (
    MAX_INGRESS_FILE_BYTES,
    MAX_MARKDOWN_BYTES,
    buffer_terminated_request_body,
    read_bounded_file,
    read_bounded_upload,
    validate_markdown_value,
)
from .csrf import register_csrf
from .security_headers import register_security_headers
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
from .xianxia_character_model import (
    XIANXIA_ATTRIBUTE_KEYS,
    XIANXIA_ATTRIBUTE_LABELS,
    XIANXIA_EFFORT_KEYS,
    XIANXIA_EFFORT_LABELS,
    XIANXIA_ENERGY_KEYS,
    XIANXIA_ITEM_NATURES,
    XIANXIA_ITEM_TYPES,
)
from .xianxia_character_builder import (
    XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT,
    build_xianxia_character_create_context,
    build_xianxia_character_definition,
    build_xianxia_character_initial_state,
)
from .xianxia_character_importer import build_xianxia_manual_import_character
from .xianxia_import_presenter import (
    build_xianxia_manual_import_context,
    build_xianxia_manual_import_payload,
    build_xianxia_manual_import_preview,
)
from .combat_presenter import DND_5E_CONDITION_OPTIONS, present_combat_tracker
from .combat_npc_resources import (
    build_npc_resource_seeds_from_markdown,
    build_npc_resource_seeds_from_systems_entry,
)
from .character_presenter import (
    XIANXIA_READ_SUBPAGE_LABELS,
    build_character_entry_href,
    format_signed,
    present_character_detail,
    present_character_roster,
    render_campaign_markdown,
    resolve_item_description_html,
)
from .character_mechanics_projection import (
    build_character_mechanics_projection,
    build_character_inventory_item_ref,
    find_item_use_action,
    parse_item_action_slot_selection,
)
from .auth_store import AuthStore
from .campaign_combat_service import (
    CampaignCombatRevisionConflictError,
    CampaignCombatService,
    CampaignCombatValidationError,
    PlayerCharacterSnapshotSyncMetrics,
)
from .campaign_combat_store import CampaignCombatStore
from .campaign_content_service import (
    CampaignContentError,
    delete_campaign_asset_file,
    delete_campaign_character_file,
    get_campaign_page_file,
    guess_campaign_asset_media_type,
    list_campaign_page_files,
    write_campaign_asset_file,
)
from .campaign_dm_content_service import CampaignDMContentService
from .campaign_dm_content_store import CampaignDMContentStore
from .campaign_page_store import CampaignPageStore
from .campaign_session_service import (
    ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS,
    CampaignSessionService,
    CampaignSessionValidationError,
)
from .campaign_session_store import CampaignSessionStore
from .character_repository import CharacterRepository, load_campaign_character_config
from .character_routes import (
    register_character_portrait_asset_route,
    register_character_read_route,
    register_character_roster_route,
    register_character_routes,
)
from .character_state_service import CharacterStateService
from .character_store import CharacterStateConflictError, CharacterStateStore
from .campaign_visibility import (
    CAMPAIGN_VISIBILITY_SCOPE_LABELS,
    CAMPAIGN_VISIBILITY_SCOPES,
    VISIBILITY_LABELS,
    VISIBILITY_PRIVATE,
    is_valid_visibility,
    list_visibility_choices,
    normalize_visibility_choice,
)
from .combat_routes import (
    register_combat_advance_turn_route,
    register_combat_basic_seeding_routes,
    register_combat_clear_route,
    register_combat_condition_routes,
    register_combat_delete_combatant_route,
    register_combat_routes,
    register_combat_set_current_turn_route,
    register_combat_update_player_detail_visibility_route,
    register_combat_update_turn_value_route,
)
from .config import Config
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
)
from .campaign_wiki_safety import (
    build_dm_player_wiki_page_summary,
    build_dm_player_wiki_removal_safety_index,
)
from .db import get_db_query_metrics, register_db, reset_db_query_metrics
from .dm_content_routes import register_dm_content_routes
from .models import section_sort_key, subsection_sort_key
from .publishing_mutations import build_dm_player_wiki_form
from .publishing_routes import register_publishing_routes, resolve_campaign_asset_file
from .session_routes import register_session_routes
from .systems_routes import register_systems_routes
from .player_choices import build_active_player_choices
from .session_article_publisher import (
    SESSION_ARTICLE_SECTION_TARGETS,
    SESSION_ARTICLE_SOURCE_REF_PREFIX,
    SessionArticlePublishError,
    build_default_publish_options,
    find_published_page_for_session_article,
    list_published_pages_for_session_articles,
    list_section_choices,
    normalize_publish_options,
    publish_session_article,
)
from .repository import Repository, normalize_lookup, slugify
from .rich_text import safe_rich_html
from .repository_store import RepositoryStore
from .session_models import (
    SESSION_ARTICLE_SOURCE_KIND_PAGE,
    SESSION_ARTICLE_SOURCE_KIND_SYSTEMS,
    build_session_article_page_source_ref,
    build_session_article_systems_source_ref,
    parse_session_article_source_ref,
)
from .session_presenter import (
    present_session_dm_passive_score_rows,
    present_session_articles,
    present_session_log_summaries,
    present_session_messages,
    present_session_record,
)
from .session_source_presenter import (
    get_pullable_session_systems_entry as get_shared_pullable_session_systems_entry,
    get_pullable_session_wiki_page_record as get_shared_pullable_session_wiki_page_record,
)
from .systems_importer import SUPPORTED_ENTRY_TYPES
from .systems_labels import (
    SYSTEMS_ENTRY_TYPE_LABELS,
    SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
    systems_entry_type_choice_labels,
    systems_entry_type_label,
    systems_entry_type_sort_key,
    systems_source_browse_intro,
)
from .systems_access import (
    filter_accessible_systems_entries as filter_shared_accessible_systems_entries,
    list_accessible_campaign_source_entries as list_shared_accessible_campaign_source_entries,
)
from .systems_service import LICENSE_CLASS_LABELS, SystemsPolicyValidationError, SystemsService
from .systems_store import SystemsStore
from .live_presenter import (
    build_combat_live_view_token as build_shared_combat_live_view_token,
    build_combat_poll_settings,
    build_session_live_view_token as build_shared_session_live_view_token,
    build_session_poll_settings,
    build_unchanged_live_payload,
    normalize_session_subpage,
    parse_live_detail_state_token_header as parse_shared_live_detail_state_token_header,
    should_short_circuit_live_response as should_short_circuit_shared_live_response,
    should_skip_selected_combatant_detail_render,
)
from .system_policy import (
    CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION,
    CHARACTER_ROUTE_LANE_DND5E,
    CHARACTER_ROUTE_LANE_XIANXIA,
    DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE,
    NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE,
    character_advancement_lane,
    character_advancement_unsupported_message,
    native_character_create_lane,
    native_character_create_unsupported_message,
    supports_character_controls_routes,
    supports_character_read_routes,
    supports_character_session_routes,
    supports_combat_tracker,
    supports_dnd5e_character_spellcasting_tools,
    supports_dnd5e_statblock_upload,
    is_dnd_5e_system,
    is_xianxia_system,
    supports_native_character_advancement,
    supports_native_character_create,
    supports_native_character_tools,
)
from .version import build_app_metadata

SESSION_ARTICLE_FORM_MODES = {"manual", "upload", "wiki"}
DM_CONTENT_SUBPAGE_LABELS = {
    "statblocks": "Statblocks",
    "player-wiki": "Player Wiki",
    "systems": "Systems",
    "staged-articles": "Staged Articles",
    "conditions": "Conditions",
}
CHARACTER_READ_SUBPAGE_LABELS = {
    "quick": "Quick Reference",
    "spellcasting": "Spellcasting",
    "features": "Features",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "personal": "Personal",
    "portrait": "Portrait",
    "notes": "Notes",
}
CHARACTER_CONTROLS_SUBPAGE_LABELS = {
    "controls": "Controls",
}
SESSION_CHARACTER_SECTION_ALIASES = {
    normalize_lookup("overview"): "overview",
    normalize_lookup("quick"): "overview",
    normalize_lookup("quick reference"): "overview",
    normalize_lookup("spells"): "spells",
    normalize_lookup("spell"): "spells",
    normalize_lookup("spellcasting"): "spells",
    normalize_lookup("resources"): "resources",
    normalize_lookup("resource"): "resources",
    normalize_lookup("features"): "features",
    normalize_lookup("feature"): "features",
    normalize_lookup("equipment"): "equipment",
    normalize_lookup("inventory"): "inventory",
    normalize_lookup("abilities and skills"): "abilities_skills",
    normalize_lookup("abilities & skills"): "abilities_skills",
    normalize_lookup("abilities_skills"): "abilities_skills",
    normalize_lookup("ability scores"): "abilities_skills",
    normalize_lookup("skills"): "abilities_skills",
    normalize_lookup("notes"): "notes",
    normalize_lookup("personal"): "personal",
}
XIANXIA_SESSION_CHARACTER_SECTION_ALIASES = {
    normalize_lookup("overview"): "quick",
    normalize_lookup("quick"): "quick",
    normalize_lookup("quick reference"): "quick",
    normalize_lookup("martial arts"): "martial_arts",
    normalize_lookup("martial_arts"): "martial_arts",
    normalize_lookup("techniques"): "techniques",
    normalize_lookup("technique"): "techniques",
    normalize_lookup("resources"): "resources",
    normalize_lookup("resource"): "resources",
    normalize_lookup("skills"): "skills",
    normalize_lookup("abilities and skills"): "skills",
    normalize_lookup("abilities & skills"): "skills",
    normalize_lookup("abilities_skills"): "skills",
    normalize_lookup("equipment"): "equipment",
    normalize_lookup("inventory"): "inventory",
    normalize_lookup("notes"): "notes",
    normalize_lookup("personal"): "personal",
}
SESSION_CHARACTER_FULL_SHEET_PAGE_MAP = {
    "overview": ("quick", "#character-quick-overview"),
    "spells": ("spellcasting", ""),
    "resources": ("quick", "#character-quick-resources"),
    "features": ("features", ""),
    "equipment": ("equipment", ""),
    "inventory": ("inventory", ""),
    "abilities_skills": ("quick", "#character-quick-abilities-skills"),
    "notes": ("notes", ""),
    "personal": ("personal", ""),
}
CHARACTER_READ_TO_SESSION_CHARACTER_PAGE_MAP = {
    "quick": "overview",
    "spellcasting": "spells",
    "features": "features",
    "equipment": "equipment",
    "inventory": "inventory",
    "personal": "personal",
    "notes": "notes",
    "controls": "overview",
}
COMBAT_AND_SESSION_COMBAT_SUMMARY = (
    "turn-by-turn movement, action economy, conditions, and turn order while the combat encounter is active"
)
SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE = "Personal details are edited outside Session Character."
SESSION_CHARACTER_ADVANCED_PERSONAL_EDIT_BLOCK_MESSAGE = (
    "Physical description and background are edited in Advanced Editor."
)
COMBAT_SUBPAGE_LABELS = {
    "combat": "Combat",
    "character": "Character",
    "status": "DM status",
    "dm": "Encounter controls",
}
COMBAT_SOURCE_LABELS = {
    COMBAT_SOURCE_KIND_CHARACTER: "Character",
    COMBAT_SOURCE_KIND_MANUAL_NPC: "Manual NPC",
    COMBAT_SOURCE_KIND_DM_STATBLOCK: "DM Content",
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER: "Systems",
}
COMBAT_NPC_WORKSPACE_SECTION_LABELS = {
    "reference": "Reference",
    "actions": "Actions",
    "bonus_actions": "Bonus Actions",
    "reactions": "Reactions",
    "legendary_actions": "Legendary Actions",
    "lair_actions": "Lair Actions",
    "traits": "Traits",
    "resources": "Resources",
    "abilities_skills": "Abilities and Skills",
}
COMBAT_NPC_WORKSPACE_SECTION_ORDER = tuple(COMBAT_NPC_WORKSPACE_SECTION_LABELS.keys())
COMBAT_NPC_WORKSPACE_SECTION_EMPTY_MESSAGES = {
    "reference": "No source-backed reference detail is recorded for this combatant.",
    "actions": "No source-backed actions are recorded for this combatant.",
    "bonus_actions": "No bonus actions are recorded for this combatant.",
    "reactions": "No reactions are recorded for this combatant.",
    "legendary_actions": "No legendary actions are recorded for this combatant.",
    "lair_actions": "No lair actions are recorded for this combatant.",
    "traits": "No source-backed traits are recorded for this combatant.",
    "resources": "No source-backed resources are recorded for this combatant.",
    "abilities_skills": "No ability or skill detail is recorded for this combatant.",
}
COMBAT_NPC_WORKSPACE_SECTION_HEADING_ALIASES = {
    normalize_lookup("reference"): "reference",
    normalize_lookup("action"): "actions",
    normalize_lookup("actions"): "actions",
    normalize_lookup("bonus action"): "bonus_actions",
    normalize_lookup("bonus actions"): "bonus_actions",
    normalize_lookup("reaction"): "reactions",
    normalize_lookup("reactions"): "reactions",
    normalize_lookup("legendary action"): "legendary_actions",
    normalize_lookup("legendary actions"): "legendary_actions",
    normalize_lookup("lair action"): "lair_actions",
    normalize_lookup("lair actions"): "lair_actions",
    normalize_lookup("trait"): "traits",
    normalize_lookup("traits"): "traits",
    normalize_lookup("resource"): "resources",
    normalize_lookup("resources"): "resources",
    normalize_lookup("abilities and skills"): "abilities_skills",
    normalize_lookup("abilities & skills"): "abilities_skills",
    normalize_lookup("ability scores"): "abilities_skills",
    normalize_lookup("skills"): "abilities_skills",
    normalize_lookup("saving throws"): "abilities_skills",
}
COMBAT_NPC_WORKSPACE_SECTION_ENTRY_ALIASES = {
    normalize_lookup("at-a-glance"): "reference",
    normalize_lookup("statblock"): "reference",
    normalize_lookup("tactics"): "reference",
    normalize_lookup("scaling notes"): "reference",
    normalize_lookup("scaling note"): "reference",
    normalize_lookup("notes"): "reference",
    normalize_lookup("note"): "reference",
    normalize_lookup("changeling"): "reference",
}
COMBAT_NPC_ABILITY_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}
COMBAT_NPC_ABILITY_ORDER = tuple(COMBAT_NPC_ABILITY_LABELS.keys())
COMBAT_NPC_HTML_HEADING_PATTERN = re.compile(
    r"<h(?P<level>[1-6])\b[^>]*>(?P<title>.*?)</h(?P=level)>",
    re.IGNORECASE | re.DOTALL,
)
COMBAT_NPC_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
COMBAT_NPC_STATBLOCK_ABILITY_PATTERN = re.compile(
    r"(?i)\b(?P<key>STR|DEX|CON|INT|WIS|CHA)\s+(?P<score>\d+)(?:\s*\((?P<modifier>[+-]?\d+)\))?"
)
COMBAT_NPC_WORKSPACE_ENTRY_HEADING_WITH_SUFFIX_PATTERN = re.compile(
    r"(?i)^(?P<name>.+?)\s*\(.*\)\s*$"
)
BUILDER_RELEVANT_CAMPAIGN_SECTIONS = frozenset(
    {
        CAMPAIGN_MECHANICS_SECTION,
        CAMPAIGN_ITEMS_SECTION,
    }
)
def normalize_session_article_form_mode(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in SESSION_ARTICLE_FORM_MODES:
        return normalized
    return "manual"


def normalize_dm_content_subpage(value: str, *, allow_default: bool = False) -> str:
    normalized = (value or "").strip().lower().replace("_", "-")
    if not normalized:
        return "statblocks" if allow_default else ""

    aliases = {
        "player-wiki": "player-wiki",
        "playerwiki": "player-wiki",
        "wiki": "player-wiki",
        "wiki-pages": "player-wiki",
        "player-wiki-pages": "player-wiki",
        "pages": "player-wiki",
        "system": "systems",
        "systems": "systems",
        "systems-management": "systems",
        "systems-settings": "systems",
        "source-management": "systems",
        "statblock": "statblocks",
        "statblocks": "statblocks",
        "staged-article": "staged-articles",
        "staged-articles": "staged-articles",
        "stagedarticles": "staged-articles",
        "condition": "conditions",
        "conditions": "conditions",
    }
    return aliases.get(normalized, "")


def build_dm_statblock_subsection_groups(statblocks) -> tuple[list[object], list[dict[str, object]]]:
    top_level_statblocks = []
    subsection_map = defaultdict(list)
    for statblock in statblocks:
        normalized_subsection = str(getattr(statblock, "subsection", "") or "").strip()
        if normalized_subsection:
            subsection_map[normalized_subsection].append(statblock)
            continue
        top_level_statblocks.append(statblock)

    top_level_statblocks.sort(key=lambda statblock: (statblock.title.lower(), statblock.id))
    subsection_groups = []
    for subsection_name in sorted(
        subsection_map,
        key=lambda subsection_name: subsection_sort_key("Statblocks", subsection_name),
    ):
        subsection_groups.append(
            {
                "name": subsection_name,
                "statblocks": sorted(
                    subsection_map[subsection_name],
                    key=lambda statblock: (statblock.title.lower(), statblock.id),
                ),
            }
        )
    return top_level_statblocks, subsection_groups


def normalize_dm_player_wiki_int(value: str, *, field_label: str, default: int = 0) -> int:
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


def build_dm_custom_systems_entry_type_choices(*, library_slug: str = "") -> list[dict[str, str]]:
    entry_type_labels = systems_entry_type_choice_labels(library_slug)
    return [
        {
            "value": entry_type,
            "label": entry_type_labels.get(entry_type, systems_entry_type_label(entry_type)),
        }
        for entry_type in sorted(entry_type_labels, key=systems_entry_type_sort_key)
    ]


def build_systems_import_entry_type_choices() -> list[dict[str, str]]:
    return [
        {
            "value": entry_type,
            "label": SYSTEMS_ENTRY_TYPE_LABELS.get(entry_type, entry_type.replace("_", " ").title()),
        }
        for entry_type in sorted(SUPPORTED_ENTRY_TYPES, key=systems_entry_type_sort_key)
    ]


def build_systems_import_form(form_data=None) -> dict[str, object]:
    selected_source_ids: list[str] = []
    selected_entry_types: list[str] = []
    import_version = ""
    if form_data is not None:
        if hasattr(form_data, "getlist"):
            selected_source_ids = [
                str(value or "").strip().upper()
                for value in form_data.getlist("source_ids")
                if str(value or "").strip()
            ]
            selected_entry_types = [
                str(value or "").strip().lower()
                for value in form_data.getlist("entry_types")
                if str(value or "").strip()
            ]
        import_version = str(form_data.get("import_version") or "").strip()

    return {
        "source_ids": selected_source_ids,
        "entry_types": selected_entry_types,
        "import_version": import_version,
    }


def build_dm_custom_systems_entry_form(
    *,
    entry=None,
    form_data=None,
    visibility: str = "players",
) -> dict[str, str]:
    data = form_data if form_data is not None else {}
    if data:
        return {
            "title": str(data.get("custom_entry_title") or ""),
            "slug_leaf": str(data.get("custom_entry_slug") or ""),
            "entry_type": str(data.get("custom_entry_type") or "rule"),
            "visibility": str(data.get("custom_entry_visibility") or "players"),
            "provenance": str(data.get("custom_entry_provenance") or ""),
            "search_metadata": str(data.get("custom_entry_search_metadata") or ""),
            "body_markdown": str(data.get("custom_entry_body_markdown") or ""),
        }
    if entry is not None:
        metadata = dict(entry.metadata or {})
        body = dict(entry.body or {})
        return {
            "title": entry.title,
            "slug_leaf": entry.slug,
            "entry_type": entry.entry_type,
            "visibility": visibility,
            "provenance": str(metadata.get("provenance") or entry.source_path or ""),
            "search_metadata": str(metadata.get("search_metadata") or ""),
            "body_markdown": str(body.get("markdown") or metadata.get("body_markdown") or ""),
        }
    return {
        "title": "",
        "slug_leaf": "",
        "entry_type": "rule",
        "visibility": visibility,
        "provenance": "",
        "search_metadata": "",
        "body_markdown": "",
    }


def custom_systems_entry_dom_id(entry) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(entry.slug or entry.id)).strip("-") or "custom-entry"


def get_character_read_subpage_labels(
    *,
    include_spellcasting: bool = False,
    include_controls: bool = False,
    xianxia_read: dict[str, object] | None = None,
) -> dict[str, str]:
    if xianxia_read:
        xianxia_labels: dict[str, str] = {}
        for subpage in list(xianxia_read.get("subpages") or []):
            if not isinstance(subpage, dict):
                continue
            slug = str(subpage.get("slug") or "").strip()
            label = str(subpage.get("label") or "").strip()
            if not slug or not label:
                continue
            if slug == "controls" and not include_controls:
                continue
            xianxia_labels[slug] = label
        if xianxia_labels:
            return xianxia_labels

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
            "portrait": CHARACTER_READ_SUBPAGE_LABELS["portrait"],
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
    xianxia_read: dict[str, object] | None = None,
) -> str:
    normalized = (value or "").strip().lower()
    if normalized in get_character_read_subpage_labels(
        include_spellcasting=include_spellcasting,
        include_controls=include_controls,
        xianxia_read=xianxia_read,
    ):
        return normalized
    return "quick"


def get_session_character_subpage_labels(
    *,
    include_spellcasting: bool = False,
    xianxia_read: dict[str, object] | None = None,
) -> dict[str, str]:
    if xianxia_read:
        return get_character_read_subpage_labels(
            include_spellcasting=False,
            include_controls=False,
            xianxia_read=xianxia_read,
        )

    labels = {
        "overview": SESSION_CHARACTER_SECTION_LABELS["overview"],
    }
    if include_spellcasting:
        labels["spells"] = SESSION_CHARACTER_SECTION_LABELS["spells"]
    labels.update(
        {
            "resources": SESSION_CHARACTER_SECTION_LABELS["resources"],
            "features": SESSION_CHARACTER_SECTION_LABELS["features"],
            "equipment": SESSION_CHARACTER_SECTION_LABELS["equipment"],
            "inventory": SESSION_CHARACTER_SECTION_LABELS["inventory"],
            "abilities_skills": SESSION_CHARACTER_SECTION_LABELS["abilities_skills"],
            "notes": SESSION_CHARACTER_SECTION_LABELS["notes"],
            "personal": SESSION_CHARACTER_SECTION_LABELS["personal"],
        }
    )
    return labels


def normalize_session_character_subpage(
    value: str,
    *,
    include_spellcasting: bool = False,
    xianxia_read: dict[str, object] | None = None,
) -> str:
    allowed_labels = get_session_character_subpage_labels(
        include_spellcasting=include_spellcasting,
        xianxia_read=xianxia_read,
    )
    normalized = normalize_lookup(value)
    if xianxia_read:
        direct_candidate = (value or "").strip().lower()
        if direct_candidate in allowed_labels:
            return direct_candidate
        candidate = XIANXIA_SESSION_CHARACTER_SECTION_ALIASES.get(normalized, "")
        if candidate in allowed_labels:
            return candidate
        return "quick"

    candidate = SESSION_CHARACTER_SECTION_ALIASES.get(normalized, "")
    if candidate in allowed_labels:
        return candidate
    return "overview"


def xianxia_read_subpage_context_for_redirect(definition) -> dict[str, object] | None:
    if not is_xianxia_system(getattr(definition, "system", "")):
        return None
    return {
        "subpages": [
            {"slug": slug, "label": label}
            for slug, label in XIANXIA_READ_SUBPAGE_LABELS
        ]
    }


def normalize_combat_return_view(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"character", "dm", "status"}:
        return normalized
    return "combat"


def normalize_combat_dm_view(value: str) -> str:
    normalized = (value or "").strip().lower()
    return "controls" if normalized == "controls" else "status"


_COMBAT_STATUS_DETAIL_HTML_CACHE_MAX_ENTRIES = 48
_COMBAT_STATUS_DETAIL_HTML_CACHE_TTL_SECONDS = 2.0
_COMBAT_STATUS_DETAIL_HTML_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_COMBAT_STATUS_DETAIL_HTML_CACHE_LOCK = Lock()


def _build_combat_status_detail_cache_key(*, campaign_slug: str, detail_view: str, token: str) -> str:
    return f"{campaign_slug}|{detail_view}|{token}"


def _get_cached_combat_status_detail_html(*, campaign_slug: str, detail_view: str, token: str) -> str | None:
    if not token:
        return None
    key = _build_combat_status_detail_cache_key(
        campaign_slug=campaign_slug,
        detail_view=detail_view,
        token=token,
    )
    now = time.monotonic()
    with _COMBAT_STATUS_DETAIL_HTML_CACHE_LOCK:
        cached = _COMBAT_STATUS_DETAIL_HTML_CACHE.get(key)
        if cached is None:
            return None
        expires_at, html = cached
        if expires_at <= now:
            _COMBAT_STATUS_DETAIL_HTML_CACHE.pop(key, None)
            return None
        _COMBAT_STATUS_DETAIL_HTML_CACHE.move_to_end(key)
        return html


def _set_cached_combat_status_detail_html(*, campaign_slug: str, detail_view: str, token: str, html: str) -> None:
    if not token:
        return
    key = _build_combat_status_detail_cache_key(
        campaign_slug=campaign_slug,
        detail_view=detail_view,
        token=token,
    )
    expires_at = time.monotonic() + _COMBAT_STATUS_DETAIL_HTML_CACHE_TTL_SECONDS
    with _COMBAT_STATUS_DETAIL_HTML_CACHE_LOCK:
        _COMBAT_STATUS_DETAIL_HTML_CACHE[key] = (expires_at, html)
        _COMBAT_STATUS_DETAIL_HTML_CACHE.move_to_end(key)
        while len(_COMBAT_STATUS_DETAIL_HTML_CACHE) > _COMBAT_STATUS_DETAIL_HTML_CACHE_MAX_ENTRIES:
            _COMBAT_STATUS_DETAIL_HTML_CACHE.popitem(last=False)


def _clear_combat_status_detail_html_cache() -> None:
    with _COMBAT_STATUS_DETAIL_HTML_CACHE_LOCK:
        _COMBAT_STATUS_DETAIL_HTML_CACHE.clear()


def _build_cached_combat_status_detail_html(
    *,
    campaign_slug: str,
    detail_view: str,
    selected_combatant_state_token: str,
    context: dict[str, object],
) -> str:
    if not selected_combatant_state_token:
        return render_template("_combat_status_detail.html", **context)

    cached_html = _get_cached_combat_status_detail_html(
        campaign_slug=campaign_slug,
        detail_view=detail_view,
        token=selected_combatant_state_token,
    )
    if cached_html is not None:
        return cached_html

    rendered_html = render_template("_combat_status_detail.html", **context)
    _set_cached_combat_status_detail_html(
        campaign_slug=campaign_slug,
        detail_view=detail_view,
        token=selected_combatant_state_token,
        html=rendered_html,
    )
    return rendered_html



def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    validate_production_secret(app.config["APP_ENV"], app.config.get("SECRET_KEY"))
    app.jinja_env.filters["safe_rich_html"] = safe_rich_html

    campaign_page_store = CampaignPageStore(
        reload_enabled=app.config["RELOAD_CONTENT"],
        scan_interval_seconds=app.config["CONTENT_SCAN_INTERVAL_SECONDS"],
    )
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
    app.extensions["login_throttle"] = LoginThrottle()
    register_db(app)
    register_csrf(app)
    register_security_headers(app)
    register_auth(app)
    register_admin(app)
    register_api(app)

    def _build_campaign_loading_media_urls(campaign_slug: str) -> list[str]:
        campaign_slug = str(campaign_slug or "").strip()
        if not campaign_slug:
            return []

        campaign = get_repository().get_campaign(campaign_slug)
        if campaign is None:
            return []

        return select_campaign_loading_image_urls(
            campaign,
            can_access_wiki=can_access_campaign_scope(campaign_slug, "wiki"),
            build_image_url=lambda _campaign, image_path: url_for(
                "campaign_asset",
                campaign_slug=_campaign.slug,
                asset_path=image_path,
            ),
            image_exists=lambda _campaign, image_path: get_campaign_asset_file(_campaign, image_path) is not None,
            max_loading_images=4,
        )

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

    if app.config["REQUEST_TRAIL_ENABLED"] or app.config["LIVE_DIAGNOSTICS"]:
        app.logger.setLevel(logging.INFO)

    REQUEST_TRAIL_IGNORED_ENDPOINTS = {
        "campaign_asset",
        "campaign_session_article_image",
        "character_portrait_asset",
        "static",
    }
    REQUEST_TRAIL_IGNORED_PATHS = {
        "/favicon.ico",
        "/healthz",
        "/livez",
        "/readyz",
    }

    def _read_proc_status_kb(field_name: str) -> int | None:
        status_path = Path("/proc/self/status")
        if not status_path.is_file():
            return None
        try:
            for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.startswith(f"{field_name}:"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    return None
                try:
                    return int(parts[1])
                except ValueError:
                    return None
        except OSError:
            return None
        return None

    _STATIC_ASSET_VERSION_CACHE: dict[str, tuple[int, int, str]] = {}

    def _resolve_static_asset_version(filename: str) -> str | None:
        if not filename:
            return None

        static_root = app.static_folder
        if not static_root:
            return None

        static_file = Path(static_root) / filename
        try:
            stat = static_file.stat()
        except OSError:
            return None

        cache_key = str(static_file.resolve())
        cache_size = len(_STATIC_ASSET_VERSION_CACHE)
        cached = _STATIC_ASSET_VERSION_CACHE.get(cache_key)
        if cached is not None:
            cached_mtime, cached_size, cached_version = cached
            if cached_mtime == int(stat.st_mtime_ns) and cached_size == stat.st_size:
                return cached_version

            if cache_size > 16:
                _STATIC_ASSET_VERSION_CACHE.clear()

        try:
            payload = static_file.read_bytes()
        except OSError:
            return None

        digest = hashlib.sha1(payload).hexdigest()[:16]
        _STATIC_ASSET_VERSION_CACHE[cache_key] = (
            int(stat.st_mtime_ns),
            stat.st_size,
            digest,
        )
        return digest

    def _build_static_asset_url(filename: str) -> str:
        version = _resolve_static_asset_version(filename)
        if version:
            return url_for("static", filename=filename, v=version)
        return url_for("static", filename=filename)

    def _build_stylesheet_url(filename: str = "styles.css") -> str:
        return _build_static_asset_url(filename)

    def _is_versioned_static_asset_request() -> bool:
        if request.endpoint != "static":
            return False
        filename = str((request.view_args or {}).get("filename") or "")
        if not filename or Path(filename).suffix.lower() not in {".css", ".js"}:
            return False
        supplied_versions = request.args.getlist("v")
        if len(supplied_versions) != 1 or not supplied_versions[0]:
            return False
        current_version = _resolve_static_asset_version(filename)
        return current_version is not None and supplied_versions[0] == current_version

    def _strip_cookie_vary_header(response):
        vary_header = response.headers.get("Vary")
        if not vary_header:
            return
        vary_headers = [
            token.strip()
            for token in vary_header.split(",")
            if token.strip().lower() != "cookie"
        ]
        if vary_headers:
            response.headers["Vary"] = ", ".join(vary_headers)
            return
        response.headers.pop("Vary", None)

    def current_request_duration_ms() -> float:
        request_started_at = getattr(g, "request_started_at", None)
        if not isinstance(request_started_at, float):
            return 0.0
        return max(0.0, (time.perf_counter() - request_started_at) * 1000)

    def resolve_request_remote_addr() -> str:
        if request.access_route:
            return str(request.access_route[0] or "")
        return str(request.remote_addr or "")

    def should_log_request_trail() -> bool:
        if not app.config["REQUEST_TRAIL_ENABLED"]:
            return False
        if request.method == "OPTIONS":
            return False
        path = str(request.path or "").strip()
        if not path or path in REQUEST_TRAIL_IGNORED_PATHS or path.startswith("/static/"):
            return False
        endpoint = str(request.endpoint or "").strip()
        if endpoint in REQUEST_TRAIL_IGNORED_ENDPOINTS:
            return False
        return True

    def build_request_trail_payload(
        *,
        response=None,
        request_time_ms: float | None = None,
        exception: BaseException | None = None,
    ) -> dict[str, object]:
        query_metrics = get_db_query_metrics()
        payload: dict[str, object] = {
            "request_id": str(getattr(g, "request_trail_id", "") or ""),
            "method": request.method,
            "path": sanitize_request_path(request.path),
            "endpoint": str(request.endpoint or ""),
            "query_count": int(query_metrics["query_count"] or 0),
            "query_time_ms": round(float(query_metrics["query_time_ms"] or 0.0), 2),
            "write_count": int(query_metrics["write_count"] or 0),
            "write_time_ms": round(float(query_metrics["write_time_ms"] or 0.0), 2),
            "commit_count": int(query_metrics["commit_count"] or 0),
            "commit_time_ms": round(float(query_metrics["commit_time_ms"] or 0.0), 2),
            "rollback_count": int(query_metrics["rollback_count"] or 0),
            "rollback_time_ms": round(float(query_metrics["rollback_time_ms"] or 0.0), 2),
            "remote_addr": resolve_request_remote_addr(),
        }
        if request.content_length is not None:
            payload["content_length"] = int(request.content_length)
        if request_time_ms is not None:
            payload["request_time_ms"] = round(max(0.0, request_time_ms), 2)
        if response is not None:
            payload["status_code"] = int(response.status_code or 0)
            response_bytes = response.calculate_content_length()
            if response_bytes is not None:
                payload["response_bytes"] = int(response_bytes)
        process_rss_kb = _read_proc_status_kb("VmRSS")
        if process_rss_kb is not None:
            payload["process_rss_kb"] = process_rss_kb
        process_hwm_kb = _read_proc_status_kb("VmHWM")
        if process_hwm_kb is not None:
            payload["process_hwm_kb"] = process_hwm_kb
        if exception is not None:
            payload["exception_type"] = type(exception).__name__
        return payload

    @app.before_request
    def initialize_request_diagnostics():
        reset_db_query_metrics()
        request_started_at = time.perf_counter()
        g.request_started_at = request_started_at
        g.live_request_started_at = request_started_at
        g.request_trail_id = secrets.token_hex(6)
        g.request_trail_should_log = should_log_request_trail()
        if getattr(g, "request_trail_should_log", False):
            app.logger.info(
                "request_trail_start %s",
                json.dumps(build_request_trail_payload(), sort_keys=True),
            )
        return None

    @app.before_request
    def enforce_request_content_envelope():
        if (
            "CONTENT_LENGTH" not in request.environ
            and request.environ.get("wsgi.input_terminated") is True
        ):
            request_body_spool = buffer_terminated_request_body(
                request.environ,
                max_content_length=int(app.config["MAX_CONTENT_LENGTH"]),
            )
            g.request_body_spool = request_body_spool
            request.__dict__.pop("content_length", None)

        # Declared bodies stay streaming. Accessing the guarded Werkzeug stream
        # performs their Content-Length check without consuming valid data.
        _ = request.stream
        return None

    def close_request_body_spool() -> None:
        request_body_spool = g.pop("request_body_spool", None)
        if request_body_spool is not None:
            request_body_spool.close()

    before_request_chain = app.before_request_funcs.setdefault(None, [])
    for request_guard in (
        initialize_request_diagnostics,
        enforce_request_content_envelope,
    ):
        before_request_chain.remove(request_guard)
    before_request_chain[0:0] = [
        initialize_request_diagnostics,
        enforce_request_content_envelope,
    ]

    @app.after_request
    def close_request_body_spool_after_response(response):
        close_request_body_spool()
        return response

    @app.teardown_request
    def close_request_body_spool_after_exception(_: BaseException | None):
        close_request_body_spool()

    @app.after_request
    def log_slow_request_trail(response):
        if not getattr(g, "request_trail_should_log", False):
            return response
        slow_log_threshold_ms = float(app.config.get("REQUEST_SLOW_LOG_THRESHOLD_MS") or 0.0)
        request_time_ms = current_request_duration_ms()
        if slow_log_threshold_ms > 0 and request_time_ms >= slow_log_threshold_ms:
            app.logger.warning(
                "slow_request %s",
                json.dumps(
                    build_request_trail_payload(
                        response=response,
                        request_time_ms=request_time_ms,
                    ),
                    sort_keys=True,
                ),
            )
        return response

    @app.after_request
    def tune_versioned_static_asset_caching(response):
        if not _is_versioned_static_asset_request():
            return response

        if app.config["APP_ENV"] == "production":
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        _strip_cookie_vary_header(response)
        return response

    @app.teardown_request
    def log_request_trail_exception(exc: BaseException | None):
        if exc is None or not getattr(g, "request_trail_should_log", False):
            return None
        app.logger.error(
            "request_exception %s",
            json.dumps(
                build_request_trail_payload(
                    request_time_ms=current_request_duration_ms(),
                    exception=exc,
                ),
                sort_keys=True,
            ),
        )
        return None

    def get_repository() -> Repository:
        return repository_store.get()

    def get_campaign_page_store() -> CampaignPageStore:
        return campaign_page_store

    def list_builder_campaign_page_records(campaign_slug: str, campaign) -> list[object]:
        return list_builder_campaign_page_records_for_store(
            get_campaign_page_store(),
            campaign_slug,
            campaign,
            relevant_sections=BUILDER_RELEVANT_CAMPAIGN_SECTIONS,
        )

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
        return resolve_campaign_asset_file(campaign, asset_path)

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
        return get_shared_pullable_session_wiki_page_record(
            campaign,
            page_ref,
            page_store=get_campaign_page_store(),
        )

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

    def build_campaign_global_search_results(
        campaign_slug: str,
        query: str,
        *,
        limit: int = 30,
    ) -> list[dict[str, str]]:
        campaign = load_campaign_context(campaign_slug)
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return []

        results: list[dict[str, str]] = []
        if can_access_campaign_scope(campaign_slug, "wiki"):
            page_records = get_campaign_page_store().search_page_records(
                campaign.slug,
                normalized_query,
                limit=max(limit, 1),
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
                        "result_id": f"wiki:{record.page_ref}",
                        "kind": "wiki",
                        "kind_label": "Wiki",
                        "title": record.page.title,
                        "subtitle": subtitle,
                        "select_label": (
                            f"{record.page.title} - Wiki - {subtitle}"
                            if subtitle
                            else f"{record.page.title} - Wiki"
                        ),
                    }
                )
                if len(results) >= limit:
                    return results

        if can_access_campaign_scope(campaign_slug, "systems"):
            systems_entries = get_systems_service().search_entries_for_campaign(
                campaign_slug,
                query=normalized_query,
                limit=max(limit, 1),
            )
            for entry in systems_entries:
                if not can_access_campaign_systems_entry(campaign_slug, entry.slug):
                    continue
                entry_type_label = SYSTEMS_ENTRY_TYPE_LABELS.get(
                    entry.entry_type,
                    entry.entry_type.replace("_", " ").title(),
                )
                results.append(
                    {
                        "result_id": f"systems:{entry.slug}",
                        "kind": "systems",
                        "kind_label": "Systems",
                        "title": entry.title,
                        "subtitle": f"{entry_type_label} / {entry.source_id}",
                        "select_label": f"{entry.title} - Systems - {entry_type_label} - {entry.source_id}",
                    }
                )
                if len(results) >= limit:
                    break

        return results

    def build_campaign_global_search_preview_context(
        campaign_slug: str,
        result_id: str,
    ) -> dict[str, object] | None:
        campaign = load_campaign_context(campaign_slug)
        kind, separator, raw_ref = result_id.partition(":")
        ref = raw_ref.strip()
        if not separator or not ref:
            return None

        if kind == "wiki":
            if not can_access_campaign_scope(campaign_slug, "wiki"):
                return None
            page_record = get_campaign_page_store().get_page_record(
                campaign.slug,
                ref,
                include_body=False,
            )
            if page_record is None or not campaign.is_page_visible(page_record.page):
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
                "campaign": campaign,
                "result_kind": "wiki",
                "result_kind_label": "Wiki article",
                "result_title": page_record.page.title,
                "result_meta": " / ".join(
                    part
                    for part in [
                        page_record.page.section,
                        page_record.page.subsection,
                        page_record.page.display_type.title(),
                    ]
                    if part
                ),
                "result_summary": (
                    page_record.page.summary
                    if page_record.page.page_type not in ["item", "spell", "mechanic"]
                    else ""
                ),
                "result_body_html": body_html,
                "result_url": url_for(
                    "page_view",
                    campaign_slug=campaign.slug,
                    page_slug=page_record.page.route_slug,
                ),
                "result_image_url": page_image_url,
                "result_image_alt": page_record.page.image_alt or page_record.page.title,
                "result_image_caption": page_record.page.image_caption,
            }

        if kind == "systems":
            if not can_access_campaign_scope(campaign_slug, "systems"):
                return None
            entry = get_systems_service().get_entry_by_slug_for_campaign(campaign_slug, ref)
            if entry is None or not can_access_campaign_systems_entry(campaign_slug, entry.slug):
                return None
            entry_type_label = SYSTEMS_ENTRY_TYPE_LABELS.get(
                entry.entry_type,
                entry.entry_type.replace("_", " ").title(),
            )
            body_html = str(entry.rendered_html or "").strip()
            if not body_html:
                body_html = (
                    "<p class=\"meta\">This Systems entry does not have rendered article content yet.</p>"
                )
            return {
                "campaign": campaign,
                "result_kind": "systems",
                "result_kind_label": "Systems entry",
                "result_title": entry.title,
                "result_meta": f"{entry_type_label} / {entry.source_id}",
                "result_summary": "",
                "result_body_html": body_html,
                "result_url": url_for(
                    "campaign_systems_entry_detail",
                    campaign_slug=campaign.slug,
                    entry_slug=entry.slug,
                ),
                "result_image_url": "",
                "result_image_alt": "",
                "result_image_caption": "",
            }

        return None

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

    def build_session_message_recipient_player_choices(campaign_slug: str) -> list[dict[str, object]]:
        store = get_auth_store()
        character_names_by_user_id: dict[int, list[str]] = {}
        character_names_by_slug = {
            record.definition.character_slug: record.definition.name
            for record in get_character_repository().list_visible_characters(campaign_slug)
        }
        for user, _membership in store.list_campaign_user_memberships(
            campaign_slug,
            statuses=("active",),
            roles=("player",),
            user_statuses=("active",),
        ):
            character_names = [
                character_names_by_slug.get(assignment.character_slug, assignment.character_slug)
                for assignment in store.list_character_assignments_for_user(
                    int(user.id),
                    campaign_slug=campaign_slug,
                )
            ]
            if character_names:
                character_names_by_user_id[int(user.id)] = character_names
        return build_active_player_choices(
            store,
            campaign_slug,
            label_mode="character_with_display_name",
            character_names_by_user_id=character_names_by_user_id,
        )

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
        return list_visible_character_page_records_for_store(
            get_campaign_page_store(),
            campaign_slug,
            campaign,
            include_body=True,
            excluded_sections={"Sessions"},
        )

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

    def build_character_item_catalog(campaign_slug: str) -> dict[str, object]:
        return build_shared_character_item_catalog(
            get_systems_service(),
            get_campaign_page_store(),
            campaign_slug,
        )

    def build_equipment_state_form_values() -> dict[str, object]:
        return {
            "is_equipped": bool(request.form.get("is_equipped")),
            "is_attuned": bool(request.form.get("is_attuned")),
            "weapon_wield_mode": request.form.get("weapon_wield_mode"),
        }

    def build_character_inventory_manager_context(
        campaign_slug: str,
        campaign,
        record,
        *,
        campaign_page_records: list[object],
        item_catalog: dict[str, object] | None = None,
    ) -> dict[str, object]:
        item_catalog = (
            item_catalog
            if item_catalog is not None
            else build_character_item_catalog(campaign_slug)
        )
        normalized_definition_equipment = _normalize_equipment_payloads(
            list(record.definition.equipment_catalog or []),
            item_catalog=item_catalog,
        )
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
        removable_item_refs: list[str] = []
        for item in normalized_definition_equipment:
            item_id = str(item.get("id") or "").strip()
            if item_id and item_id in inventory_by_ref and not bool(item.get("is_currency_only")):
                removable_item_refs.append(item_id)
            if str(item.get("source_kind") or "").strip() != "manual_edit":
                continue
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
            "removable_item_refs": sorted({item_ref for item_ref in removable_item_refs if item_ref}),
            "supplemental_items": sorted(
                supplemental_items,
                key=lambda item: (str(item["name"]).lower(), str(item["id"]).lower()),
            ),
        }

    def build_character_equipment_state_context(
        campaign_slug: str,
        campaign,
        record,
        *,
        item_catalog: dict[str, object] | None = None,
        campaign_page_records: list[object] | None = None,
    ) -> dict[str, object]:
        item_catalog = (
            item_catalog
            if item_catalog is not None
            else build_character_item_catalog(campaign_slug)
        )
        definition_item_lookup, support_lookup = build_record_equipment_support_lookup(
            record,
            item_catalog=item_catalog,
        )
        equipment_items: list[dict[str, object]] = []
        for inventory_item in list((record.state_record.state or {}).get("inventory") or []):
            item_ref = build_character_inventory_item_ref(inventory_item)
            if not item_ref:
                continue
            definition_item = definition_item_lookup.get(item_ref, {})
            support = dict(support_lookup.get(item_ref) or {})
            if not bool(support.get("supports_equipped_state")):
                continue
            support_item = {
                **dict(definition_item or {}),
                **dict(inventory_item or {}),
            }
            systems_ref = dict(definition_item.get("systems_ref") or {})
            page_ref = normalize_character_page_ref(definition_item.get("page_ref"))
            href = build_character_entry_href(
                campaign.slug,
                systems_ref=systems_ref,
                page_ref=definition_item.get("page_ref"),
            )
            requires_attunement = bool(support.get("requires_attunement"))
            resolved_weapon_wield_mode = resolve_weapon_wield_mode(
                support_item,
                item_catalog=item_catalog,
                support=support,
            )
            supports_weapon_wield_mode = bool(support.get("supports_weapon_wield_mode"))
            is_equipped = bool(resolved_weapon_wield_mode) if supports_weapon_wield_mode else bool(
                inventory_item.get("is_equipped", False)
            )
            equipped_label = (
                weapon_wield_mode_label(resolved_weapon_wield_mode)
                if supports_weapon_wield_mode and is_equipped
                else "Equipped"
                if is_equipped
                else "Not equipped"
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
                    "description_html": (
                        resolve_item_description_html(
                            campaign,
                            definition_item,
                            systems_service=get_systems_service(),
                            campaign_page_records=campaign_page_records,
                        )
                        if href
                        else ""
                    ),
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
            "equipment_item_refs": [str(item.get("id") or "").strip() for item in equipment_items if str(item.get("id") or "").strip()],
            "attunable_item_refs": [
                str(item.get("id") or "").strip()
                for item in equipment_items
                if bool(item.get("requires_attunement")) and str(item.get("id") or "").strip()
            ],
            "at_attunement_limit": attuned_count >= max_attuned_items if max_attuned_items > 0 else True,
            "over_attunement_limit": attuned_count > max_attuned_items,
        }

    def build_projected_item_use_actions(campaign_slug: str, campaign, record) -> list[dict[str, object]]:
        projection = build_character_mechanics_projection(
            campaign=campaign,
            definition=record.definition,
            state=record.state_record.state,
            systems_service=get_systems_service(),
            campaign_page_records=list_visible_character_page_records(campaign_slug, campaign),
        )
        return [
            dict(action or {})
            for action in list(projection.get("item_use_actions") or [])
            if isinstance(action, dict)
        ]

    def resolve_projected_item_use_action(campaign_slug: str, campaign, record, action_id: str) -> dict[str, object]:
        action = find_item_use_action(
            build_projected_item_use_actions(campaign_slug, campaign, record),
            action_id,
        )
        if action is None:
            raise ValueError("Choose a modeled item action for this character.")
        return action

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

    def load_character_spell_management_support(
        campaign_slug: str,
        definition,
        *,
        spell_catalog: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        resolved_spell_catalog = (
            spell_catalog
            if spell_catalog is not None
            else _build_spell_catalog(
                _list_campaign_enabled_entries(
                    get_systems_service(),
                    campaign_slug,
                    "spell",
                )
            )
        )
        selected_class_rows = resolve_character_spellcasting_class_entries(campaign_slug, definition)
        return resolved_spell_catalog, selected_class_rows

    def build_character_spell_manager_context(
        campaign_slug: str,
        campaign,
        record,
        *,
        spell_catalog: dict[str, object] | None = None,
        selected_class_rows: list[dict[str, object]] | None = None,
    ) -> dict[str, object] | None:
        resolved_spell_catalog, resolved_class_rows = load_character_spell_management_support(
            campaign_slug,
            record.definition,
            spell_catalog=spell_catalog,
        )
        if selected_class_rows is not None:
            resolved_class_rows = selected_class_rows
        manager = build_character_spell_management_context(
            record.definition,
            spell_catalog=resolved_spell_catalog,
            selected_class_rows=resolved_class_rows,
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
                "spell_level_sections": [],
                "row_kind": str(section.get("row_kind") or "class").strip() or "class",
                "spell_mode": str(section.get("mode") or "").strip(),
            }
            for section in sections
        ]
        current_row_sections = [dict(section) for section in row_sections]
        return {
            "spellcasting_class": str(primary_section.get("title") or "Spellcasting").strip() or "Spellcasting",
            "spellcasting_ability": str(primary_section.get("spellcasting_ability") or "").strip(),
            "spell_save_dc": primary_section.get("spell_save_dc"),
            "spell_attack_bonus": str(primary_section.get("spell_attack_bonus") or "").strip(),
            "slots": [],
            "slots_title": "",
            "slot_pools": [],
            "multiclass_summary": "",
            "row_sections": current_row_sections,
            "current_row_sections": current_row_sections,
            "preparation_row_sections": [],
            "is_multiclass": len(row_sections) > 1,
        }

    def validate_character_portrait_upload(upload) -> tuple[str, bytes]:
        return prepare_character_portrait_file(
            str(getattr(upload, "filename", "") or ""),
            (
                read_bounded_upload(
                    upload,
                    max_bytes=MAX_INGRESS_FILE_BYTES,
                    message="Character portraits must stay under 8 MB.",
                )
                if upload is not None
                else b""
            ),
        )

    def build_character_portrait_context(campaign, definition) -> dict[str, str] | None:
        portrait = character_portrait_profile(definition)
        asset_ref = str(portrait["asset_ref"])
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
            "alt": str(portrait["alt_text"]),
            "caption": str(portrait["caption"]),
        }

    def finalize_character_definition_for_write(
        campaign_slug: str,
        definition,
        *,
        campaign=None,
    ):
        resolved_campaign = campaign or load_campaign_context(campaign_slug)
        if not campaign_supports_native_character_tools(resolved_campaign):
            return definition
        return normalize_definition_to_native_model(
            definition,
            item_catalog=build_character_item_catalog(campaign_slug),
            systems_service=get_systems_service(),
        )

    def redirect_to_character_mode(campaign_slug: str, character_slug: str, *, anchor: str | None = None):
        if is_session_character_return_requested(campaign_slug, character_slug):
            return redirect_to_campaign_session_character(
                campaign_slug,
                character_slug,
                anchor=anchor,
            )
        campaign, record = load_character_context(campaign_slug, character_slug)
        spellcasting_payload = dict(record.definition.spellcasting or {})
        read_subpage = normalize_character_read_subpage(
            request.values.get("page", ""),
            include_spellcasting=bool(
                campaign_supports_dnd5e_character_spellcasting_tools(campaign)
                and (
                    spellcasting_payload.get("spells")
                    or spellcasting_payload.get("slot_progression")
                    or spellcasting_payload.get("slot_lanes")
                )
            ),
            include_controls=(
                has_session_mode_access(campaign_slug, character_slug)
                and campaign_supports_character_controls_routes(campaign)
            ),
            xianxia_read=xianxia_read_subpage_context_for_redirect(record.definition),
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

    def redirect_to_campaign_session_character(
        campaign_slug: str,
        character_slug: str,
        *,
        anchor: str | None = None,
        confirm_rest: str | None = None,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        spellcasting_payload = dict(record.definition.spellcasting or {})
        session_subpage = normalize_session_character_subpage(
            request.values.get("page", ""),
            include_spellcasting=bool(
                campaign_supports_dnd5e_character_spellcasting_tools(campaign)
                and (
                    spellcasting_payload.get("spells")
                    or spellcasting_payload.get("slot_progression")
                    or spellcasting_payload.get("slot_lanes")
                )
            ),
            xianxia_read=xianxia_read_subpage_context_for_redirect(record.definition),
        )
        route_values: dict[str, object] = {
            "campaign_slug": campaign_slug,
            "character": character_slug,
            "page": session_subpage,
            "_anchor": anchor,
        }
        normalized_confirm_rest = str(confirm_rest or "").strip().lower()
        if normalized_confirm_rest in {"short", "long"}:
            route_values["confirm_rest"] = normalized_confirm_rest
        if is_async_request() and request.values.get("fragment") == "1":
            route_values["fragment"] = "1"
        return redirect(url_for("campaign_session_character_view", **route_values))

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
        combat_dm_view: str | None = None,
    ):
        route_values = {
            "campaign_slug": campaign_slug,
            "combatant": combatant_id,
            "_anchor": anchor,
        }
        if normalize_combat_dm_view(combat_dm_view or "") == "controls":
            route_values["view"] = "controls"
        return redirect(
            url_for(
                "campaign_combat_dm_view",
                **route_values,
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
        article_mode: str | None = None,
        subpage: str | None = None,
    ):
        normalized_subpage = normalize_dm_content_subpage(subpage or "")
        if normalized_subpage:
            return redirect(
                url_for(
                    "campaign_dm_content_subpage_view",
                    campaign_slug=campaign_slug,
                    dm_content_subpage=normalized_subpage,
                    article_mode=article_mode or None,
                    _anchor=anchor,
                )
            )
        return redirect(
            url_for(
                "campaign_dm_content_view",
                campaign_slug=campaign_slug,
                article_mode=article_mode or None,
                _anchor=anchor,
            )
        )

    def is_async_request() -> bool:
        return request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"

    def render_flash_stack_html() -> str:
        return render_template("_flash_stack.html")

    def parse_live_detail_state_token_header() -> str:
        return parse_shared_live_detail_state_token_header(request.headers)

    def attach_live_response_diagnostics(
        response,
        *,
        view_name: str,
        changed: bool,
        state_check_ms: float,
        render_ms: float,
        snapshot_sync_metrics: PlayerCharacterSnapshotSyncMetrics | None = None,
        live_revision: int | None = None,
    ):
        query_metrics = get_db_query_metrics()
        query_count = int(query_metrics["query_count"] or 0)
        query_time_ms = float(query_metrics["query_time_ms"] or 0.0)
        write_count = int(query_metrics["write_count"] or 0)
        write_time_ms = float(query_metrics["write_time_ms"] or 0.0)
        commit_count = int(query_metrics["commit_count"] or 0)
        commit_time_ms = float(query_metrics["commit_time_ms"] or 0.0)
        rollback_count = int(query_metrics["rollback_count"] or 0)
        rollback_time_ms = float(query_metrics["rollback_time_ms"] or 0.0)
        request_started_at = getattr(g, "live_request_started_at", None)
        request_time_ms = (
            (time.perf_counter() - request_started_at) * 1000
            if isinstance(request_started_at, float)
            else state_check_ms + render_ms
        )
        payload_bytes = len(response.get_data())
        live_response_summary = {
            "view": view_name,
            "path": sanitize_request_path(request.path),
            "changed": changed,
            "live_revision": live_revision,
            "query_count": query_count,
            "query_time_ms": round(query_time_ms, 2),
            "request_time_ms": round(request_time_ms, 2),
            "state_check_ms": round(state_check_ms, 2),
            "render_ms": round(render_ms, 2),
            "write_count": write_count,
            "write_time_ms": round(write_time_ms, 2),
            "commit_count": commit_count,
            "commit_time_ms": round(commit_time_ms, 2),
            "rollback_count": rollback_count,
            "rollback_time_ms": round(rollback_time_ms, 2),
            "payload_bytes": payload_bytes,
        }
        if snapshot_sync_metrics is not None:
            live_response_summary.update(snapshot_sync_metrics.to_diagnostics_payload())

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
            response.headers["X-Live-Write-Count"] = str(write_count)
            response.headers["X-Live-Write-Time-Ms"] = f"{write_time_ms:.2f}"
            response.headers["X-Live-Commit-Count"] = str(commit_count)
            response.headers["X-Live-Commit-Time-Ms"] = f"{commit_time_ms:.2f}"
            response.headers["X-Live-Request-Time-Ms"] = f"{request_time_ms:.2f}"
            response.headers["X-Live-View"] = view_name
            if snapshot_sync_metrics is not None:
                response.headers["X-Live-Snapshot-Sync"] = json.dumps(
                    snapshot_sync_metrics.to_diagnostics_payload(),
                    sort_keys=True,
                )
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
        snapshot_sync_metrics: PlayerCharacterSnapshotSyncMetrics | None = None,
    ):
        response = jsonify(payload)
        return attach_live_response_diagnostics(
            response,
            view_name=view_name,
            changed=changed,
            live_revision=live_revision,
            state_check_ms=state_check_ms,
            render_ms=render_ms,
            snapshot_sync_metrics=snapshot_sync_metrics,
        )

    def build_combat_live_metadata(
        campaign_slug: str,
        combat_subpage: str,
        *,
        selected_combatant_id: int | None = None,
        combat_dm_view: str | None = None,
    ) -> dict[str, object]:
        combat_service = get_campaign_combat_service()
        snapshot_sync_metrics = combat_service.sync_player_character_snapshots(
            campaign_slug,
            blocking=False,
        )
        if selected_combatant_id is None:
            selected_combatant_id = parse_requested_combatant_id()
        return {
            "snapshot_sync_metrics": snapshot_sync_metrics,
            "live_revision": combat_service.get_live_revision(campaign_slug),
            "live_view_token": build_shared_combat_live_view_token(
                campaign_slug,
                combat_subpage,
                selected_combatant_id=selected_combatant_id,
                combat_dm_view=combat_dm_view,
                can_manage_combat=can_manage_campaign_combat(campaign_slug),
                owned_character_slugs=get_owned_character_slugs(campaign_slug),
                normalize_combat_dm_view=normalize_combat_dm_view,
            ),
        }

    def build_session_live_metadata(campaign_slug: str, session_subpage: str) -> dict[str, object]:
        session_service = get_campaign_session_service()
        current_preferences = get_current_user_preferences()
        return {
            "live_revision": session_service.get_live_revision(campaign_slug),
            "live_view_token": build_shared_session_live_view_token(
                campaign_slug,
                session_subpage,
                session_chat_order=current_preferences.session_chat_order,
                can_manage_session=can_manage_campaign_session(campaign_slug),
                can_post_session_messages=can_post_campaign_session_messages(campaign_slug),
            ),
        }

    def build_session_manager_state_token(
        *,
        active_session_id: int | None,
        staged_articles: list[dict[str, object]],
        revealed_articles: list[dict[str, object]],
        session_logs: list[dict[str, object]],
    ) -> str:
        def article_token(article: dict[str, object]) -> str:
            payload = [
                str(article.get("id") or ""),
                str(article.get("status") or ""),
                str(article.get("title") or ""),
                str(article.get("source_page_ref") or ""),
                str(article.get("source_title") or ""),
                str(article.get("source_url") or ""),
                str(article.get("body_markdown") or ""),
                str(article.get("image_url") or ""),
                str(article.get("image_alt") or ""),
                str(article.get("image_caption") or ""),
                str(article.get("converted_page_title") or ""),
                str(article.get("converted_page_url") or ""),
                str(article.get("converted_page_reveal_after_session") or ""),
            ]
            digest = hashlib.sha1(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
            return f"{article.get('id') or ''}:{digest}"

        staged_ids = ",".join(article_token(article) for article in staged_articles)
        revealed_ids = ",".join(article_token(article) for article in revealed_articles)
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
                        str(combatant.get("dexterity_modifier", "")),
                        str(combatant.get("initiative_priority", "")),
                        str(combatant.get("current_hp", "")),
                        str(combatant.get("max_hp", "")),
                        str(combatant.get("temp_hp", "")),
                        str(combatant.get("movement_total", "")),
                        str(combatant.get("movement_remaining", "")),
                        "1" if combatant.get("has_action") else "0",
                        "1" if combatant.get("has_bonus_action") else "0",
                        "1" if combatant.get("has_reaction") else "0",
                        "1" if combatant.get("is_current_turn") else "0",
                        str(combatant.get("source_identity", "")),
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
                "combatants": [
                    {
                        **selected_combatant,
                        "source_identity": "|".join(
                            [
                                str(selected_combatant.get("source_kind", "")),
                                str(selected_combatant.get("source_ref", "")),
                                str(selected_combatant.get("combatant_revision", "")),
                                str(selected_combatant.get("state_revision", "")),
                            ]
                        ),
                    }
                ],
            }
        )

    def parse_expected_revision() -> int:
        raw_value = request.form.get("expected_revision", "").strip()
        if not raw_value:
            raise ValueError("Missing sheet revision. Refresh the page and try again.")
        return int(raw_value)

    def parse_expected_combatant_revision() -> int | None:
        raw_value = request.form.get("expected_combatant_revision", "").strip()
        if not raw_value:
            return None
        return int(raw_value)

    def parse_hit_dice_current_values() -> dict[int, str] | None:
        values: dict[int, str] = {}
        for key, value in request.form.items():
            if not key.startswith("hit_dice_d"):
                continue
            raw_faces = key.removeprefix("hit_dice_d").strip()
            if not raw_faces:
                continue
            try:
                faces = int(raw_faces)
            except ValueError:
                continue
            values[faces] = value
        return values or None

    def get_owned_character_slugs(campaign_slug: str) -> set[str]:
        user = get_current_user()
        if user is None:
            return set()
        assignments = get_auth_store().list_character_assignments_for_user(
            user.id,
            campaign_slug=campaign_slug,
        )
        return {assignment.character_slug for assignment in assignments}

    def can_access_session_character_surface(campaign_slug: str, character_slug: str) -> bool:
        if not can_access_campaign_scope(campaign_slug, "session"):
            return False
        if can_manage_campaign_session(campaign_slug):
            return True
        return character_slug in get_owned_character_slugs(campaign_slug)

    def is_session_character_return_requested(campaign_slug: str, character_slug: str) -> bool:
        return (
            request.values.get("return_view", "").strip().lower() == "session-character"
            and can_access_session_character_surface(campaign_slug, character_slug)
        )

    def ensure_active_session_for_session_character_mutation(
        campaign_slug: str,
        character_slug: str,
        *,
        anchor: str,
    ):
        if not is_session_character_return_requested(campaign_slug, character_slug):
            return None
        if get_campaign_session_service().get_active_session(campaign_slug) is not None:
            return None
        flash(
            "The live session has ended. Session character editing is no longer available.",
            "error",
        )
        return redirect_to_campaign_session_character(
            campaign_slug,
            character_slug,
            anchor=anchor,
        )

    def list_session_accessible_character_records(campaign_slug: str):
        return [
            record
            for record in get_character_repository().list_visible_characters(campaign_slug)
            if can_access_session_character_surface(campaign_slug, record.definition.character_slug)
        ]

    def get_default_session_character_slug(
        campaign_slug: str,
        *,
        accessible_records=None,
    ) -> str | None:
        owned_character_slugs = get_owned_character_slugs(campaign_slug)
        if not owned_character_slugs:
            return None
        records = (
            accessible_records
            if accessible_records is not None
            else list_session_accessible_character_records(campaign_slug)
        )
        for record in records:
            character_slug = record.definition.character_slug
            if character_slug in owned_character_slugs:
                return character_slug
        return None

    def build_session_character_read_view_url(
        campaign_slug: str,
        character_slug: str,
        session_subpage: str,
        *,
        xianxia_read: dict[str, object] | None = None,
    ) -> str:
        if xianxia_read:
            read_page = normalize_session_character_subpage(
                session_subpage,
                xianxia_read=xianxia_read,
            )
            anchor = ""
        else:
            read_page, anchor = SESSION_CHARACTER_FULL_SHEET_PAGE_MAP.get(
                session_subpage,
                ("quick", ""),
            )
        href = url_for(
            "character_read_view",
            campaign_slug=campaign_slug,
            character_slug=character_slug,
            page=read_page,
        )
        return f"{href}{anchor}" if anchor else href

    def find_tracked_player_combatant_for_character(
        campaign_slug: str,
        character_slug: str,
        *,
        campaign=None,
    ):
        if not character_slug:
            return None
        campaign = campaign if campaign is not None else load_campaign_context(campaign_slug)
        if not supports_combat_tracker(campaign.system):
            return None
        for combatant in get_campaign_combat_service().list_combatants(
            campaign_slug,
            sync_player_character_snapshots=False,
        ):
            if combatant.is_player_character and combatant.character_slug == character_slug:
                return combatant
        return None

    def build_session_character_empty_state(
        campaign_slug: str,
        *,
        can_manage_session: bool,
        accessible_records: list[object],
    ) -> tuple[str, str]:
        if can_manage_session:
            return (
                "No session character available",
                "No active visible characters are available to open from the Session feature right now.",
            )

        role = get_campaign_role(campaign_slug)
        if role == "observer":
            return (
                "Character tab unavailable",
                "Observers stay on the main Session page. Only assigned players, DMs, and admins "
                "can open the Character surface.",
            )
        if role == "player":
            return (
                "No session character available",
                "This account does not currently have a session-enabled character assigned in this "
                "campaign. Assigned players can open only their own session-enabled character here.",
            )
        if accessible_records:
            return (
                "No session character available",
                "No session-enabled character is available to open right now.",
            )
        return (
            "Character tab unavailable",
            "Only assigned players, DMs, and admins can open the Session character surface.",
        )

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

    def build_combat_surface_urls(
        campaign_slug: str,
        *,
        combat_subpage: str,
        selected_combatant_id: int | None = None,
        combat_dm_view: str | None = None,
    ) -> dict[str, str]:
        route_values = build_combat_route_values(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
        )
        if combat_subpage == "dm":
            normalized_dm_view = normalize_combat_dm_view(combat_dm_view or "")
            if normalized_dm_view == "controls":
                route_values["view"] = "controls"
        view_endpoint = {
            "combat": "campaign_combat_view",
            "dm": "campaign_combat_dm_view",
            "status": "campaign_combat_status_view",
        }.get(combat_subpage)
        live_endpoint = {
            "combat": "campaign_combat_live_state",
            "dm": "campaign_combat_dm_live_state",
            "status": "campaign_combat_status_live_state",
        }.get(combat_subpage)
        if view_endpoint is None or live_endpoint is None:
            return {"page_url": "", "live_url": ""}
        return {
            "page_url": url_for(view_endpoint, **route_values),
            "live_url": url_for(live_endpoint, **route_values),
        }

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
            dm_route_values = dict(focused_route_values)
            dm_route_values["view"] = "controls"
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
                    "href": url_for("campaign_combat_dm_view", **dm_route_values),
                    "is_active": current_subpage == "dm",
                }
            )
        return subpages

    def require_supported_combat_system(campaign_slug: str):
        campaign = load_campaign_context(campaign_slug)
        if not supports_combat_tracker(campaign.system):
            flash(
                f"Combat tracker support for {campaign.system or 'this system'} is not available yet.",
                "error",
            )
            return None
        return campaign

    def campaign_supports_native_character_tools(campaign) -> bool:
        return supports_native_character_tools(getattr(campaign, "system", ""))

    def campaign_supports_native_character_create(campaign) -> bool:
        return supports_native_character_create(getattr(campaign, "system", ""))

    def campaign_supports_native_character_advancement(campaign) -> bool:
        return supports_native_character_advancement(getattr(campaign, "system", ""))

    def campaign_supports_dnd5e_character_spellcasting_tools(campaign) -> bool:
        return supports_dnd5e_character_spellcasting_tools(getattr(campaign, "system", ""))

    def campaign_supports_character_read_routes(campaign) -> bool:
        return supports_character_read_routes(getattr(campaign, "system", ""))

    def campaign_supports_character_session_routes(campaign) -> bool:
        return supports_character_session_routes(getattr(campaign, "system", ""))

    def campaign_supports_character_controls_routes(campaign) -> bool:
        return supports_character_controls_routes(getattr(campaign, "system", ""))

    def redirect_unsupported_native_character_tools(
        campaign_slug: str,
        *,
        character_slug: str | None = None,
        message: str | None = None,
    ):
        flash(message or NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE, "error")
        if character_slug is None:
            return redirect(url_for("character_roster_view", campaign_slug=campaign_slug))
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    def redirect_unsupported_dnd5e_character_spellcasting_tools(
        campaign_slug: str,
        character_slug: str,
    ):
        flash(DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE, "error")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        )

    def build_campaign_help_context(campaign_slug: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        return build_shared_campaign_help_context(campaign_slug, campaign=campaign)





    app.extensions["campaign_help_context_builder"] = build_campaign_help_context

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
        if not campaign_supports_character_read_routes(campaign):
            abort(404)
        native_character_tools_supported = campaign_supports_native_character_tools(campaign)
        dnd5e_spellcasting_tools_supported = campaign_supports_dnd5e_character_spellcasting_tools(campaign)
        can_use_session_mode = (
            has_session_mode_access(campaign_slug, character_slug)
            and campaign_supports_character_session_routes(campaign)
        )
        can_manage_character = can_manage_campaign_session(campaign_slug)
        campaign_page_records = list_visible_character_page_records(campaign_slug, campaign)
        builder_campaign_page_records = list_builder_campaign_page_records(campaign_slug, campaign)
        shared_item_catalog: dict[str, object] | None = None
        shared_spell_catalog: dict[str, object] | None = None
        advancement_lane = character_advancement_lane(getattr(campaign, "system", ""))

        def get_read_item_catalog() -> dict[str, object]:
            nonlocal shared_item_catalog
            if shared_item_catalog is None:
                shared_item_catalog = build_character_item_catalog(campaign_slug)
            return shared_item_catalog

        def get_read_spell_catalog() -> dict[str, object]:
            nonlocal shared_spell_catalog
            if shared_spell_catalog is None:
                shared_spell_catalog = _build_spell_catalog(
                    _list_campaign_enabled_entries(
                        app.extensions["systems_service"],
                        campaign_slug,
                        "spell",
                    )
                )
            return shared_spell_catalog

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
                campaign_page_records=builder_campaign_page_records,
            )
            if can_use_session_mode and native_character_tools_supported
            else None
        )
        linked_feature_authoring = build_linked_feature_authoring_support(
            record.definition,
            readiness=level_up_readiness,
        )
        can_level_up = bool(
            can_use_session_mode
            and level_up_readiness
            and level_up_readiness.get("status") == "ready"
        )
        can_prepare_level_up = bool(
            can_manage_character
            and level_up_readiness
            and level_up_readiness.get("status") == "repairable"
        )
        can_use_xianxia_cultivation = bool(
            can_manage_character
            and advancement_lane == CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
            and is_xianxia_system(getattr(record.definition, "system", ""))
        )
        can_retrain = False
        if retraining_page_records and bool(linked_feature_authoring.get("supported")):
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
                spell_catalog=get_read_spell_catalog(),
            )
            can_retrain = bool(retraining_context.get("feature_rows"))
        include_controls_subpage = (
            can_use_session_mode and campaign_supports_character_controls_routes(campaign)
        )
        requested_mode = request.values.get("mode", "").strip().lower()
        requested_session_mode = requested_mode == "session"
        # Session mode for the legacy read-path is now a compatibility-only URL hint.
        # Keep full-character reads in the read shell while preserving the requested page.
        is_session_mode = False
        character_read_mode_param = "session" if (requested_session_mode and can_use_session_mode) else None

        confirm_rest = (
            request.values.get("confirm_rest", "").strip().lower()
            if requested_session_mode and can_use_session_mode
            else ""
        )
        rest_preview = None
        if confirm_rest in {"short", "long"}:
            rest_preview = get_character_state_service().preview_rest(record, confirm_rest)

        character = present_character_detail(
            campaign,
            record,
            include_player_notes_section=not is_session_mode,
            systems_service=get_systems_service(),
            campaign_page_records=campaign_page_records,
        )
        if notes_draft is not None:
            character["player_notes_markdown"] = notes_draft
        if physical_description_draft is not None:
            character["physical_description_markdown"] = physical_description_draft
        if background_draft is not None:
            character["personal_background_markdown"] = background_draft
        character["portrait"] = build_character_portrait_context(campaign, record.definition)
        spell_manager = None
        if dnd5e_spellcasting_tools_supported:
            spell_catalog = get_read_spell_catalog()
            spell_manager = build_character_spell_manager_context(
                campaign_slug,
                campaign,
                record,
                spell_catalog=spell_catalog,
            )
            if not character.get("spellcasting") and spell_manager is not None:
                spellcasting_placeholder = build_character_spellcasting_placeholder(spell_manager)
                if spellcasting_placeholder is not None:
                    character["spellcasting"] = spellcasting_placeholder
        else:
            character.pop("spellcasting", None)
        include_spellcasting_subpage = bool(character.get("spellcasting"))
        xianxia_read_context = (
            dict(character.get("xianxia_read") or {})
            if isinstance(character.get("xianxia_read"), dict)
            else None
        )
        available_character_subpages = get_character_read_subpage_labels(
            include_spellcasting=include_spellcasting_subpage,
            include_controls=include_controls_subpage,
            xianxia_read=xianxia_read_context,
        )
        character_subpage = normalize_character_read_subpage(
            request.values.get("page", ""),
            include_spellcasting=include_spellcasting_subpage,
            include_controls=include_controls_subpage,
            xianxia_read=xianxia_read_context,
        )

        character_controls = (
            build_character_controls_context(campaign_slug, character_slug)
            if include_controls_subpage
            else None
        )
        item_catalog = get_read_item_catalog()
        inventory_manager = (
            build_character_inventory_manager_context(
                campaign_slug,
                campaign,
                record,
                campaign_page_records=campaign_page_records,
                item_catalog=item_catalog,
            )
            if can_use_session_mode
            else None
        )
        equipment_state_manager = build_character_equipment_state_context(
            campaign_slug,
            campaign,
            record,
            item_catalog=item_catalog,
            campaign_page_records=campaign_page_records,
        )
        character_subpages = [
            {
                "slug": slug,
                "label": label,
                "href": url_for(
                    "character_read_view",
                    campaign_slug=campaign.slug,
                    character_slug=character["slug"],
                    mode=character_read_mode_param,
                    page=slug,
                ),
                "is_active": slug == character_subpage,
            }
            for slug, label in available_character_subpages.items()
        ]
        character_session_surface_href = ""
        if (
            is_session_mode
            and get_campaign_session_service().get_active_session(campaign_slug) is not None
            and can_access_session_character_surface(campaign_slug, character_slug)
        ):
            session_character_page = (
                normalize_session_character_subpage(
                    character_subpage,
                    xianxia_read=xianxia_read_context,
                )
                if xianxia_read_context
                else CHARACTER_READ_TO_SESSION_CHARACTER_PAGE_MAP.get(
                    character_subpage,
                    "overview",
                )
            )
            character_session_surface_href = url_for(
                "campaign_session_character_view",
                campaign_slug=campaign.slug,
                character=character_slug,
                page=session_character_page,
            )
        character_combat_surface_href = ""
        character_combat_surface_action_label = ""
        if is_session_mode and can_access_campaign_scope(campaign_slug, "combat"):
            tracked_combatant = find_tracked_player_combatant_for_character(
                campaign_slug,
                character_slug,
                campaign=campaign,
            )
            if tracked_combatant is not None:
                if can_manage_campaign_combat(campaign_slug):
                    character_combat_surface_action_label = "Open encounter status"
                    character_combat_surface_href = url_for(
                        "campaign_combat_status_view",
                        campaign_slug=campaign.slug,
                        combatant=tracked_combatant.id,
                    )
                elif character_slug in get_owned_character_slugs(campaign_slug):
                    character_combat_surface_action_label = "Open Combat"
                    character_combat_surface_href = url_for(
                        "campaign_combat_view",
                        campaign_slug=campaign.slug,
                        combatant=tracked_combatant.id,
                    )

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
                can_prepare_level_up=can_prepare_level_up,
                can_use_xianxia_cultivation=can_use_xianxia_cultivation,
                can_retrain=can_retrain,
                level_up_readiness=level_up_readiness,
                linked_feature_authoring_message=(
                    str(linked_feature_authoring.get("message") or "").strip()
                    if can_use_session_mode and not bool(linked_feature_authoring.get("supported"))
                    else ""
                ),
                is_session_mode=is_session_mode,
                character_session_surface_href=character_session_surface_href,
                character_combat_surface_href=character_combat_surface_href,
                character_combat_surface_action_label=character_combat_surface_action_label,
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
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        inactive_session_redirect = ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor=anchor,
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect

        try:
            expected_revision = parse_expected_revision()
            result = action(record)
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

    def render_xianxia_character_create_page(
        campaign_slug: str,
        create_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign = load_campaign_context(campaign_slug)
        return (
            render_template(
                "character_create_xianxia.html",
                campaign=campaign,
                builder=create_context,
                active_nav="characters",
            ),
            status_code,
        )

    def render_xianxia_manual_import_page(
        campaign_slug: str,
        import_context: dict[str, object],
        *,
        status_code: int = 200,
    ):
        campaign = load_campaign_context(campaign_slug)
        return (
            render_template(
                "character_import_xianxia_manual.html",
                campaign=campaign,
                import_context=import_context,
                active_nav="characters",
            ),
            status_code,
        )

    def render_character_edit_page(
        campaign_slug: str,
        character_slug: str,
        edit_context: dict[str, object],
        *,
        campaign_page_records: list[object] | None = None,
        status_code: int = 200,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        resolved_campaign_page_records = (
            campaign_page_records
            if campaign_page_records is not None
            else list_visible_character_page_records(campaign_slug, campaign)
        )
        return (
            render_template(
                "character_edit.html",
                campaign=campaign,
                character=present_character_detail(
                    campaign,
                    record,
                    include_player_notes_section=True,
                    systems_service=get_systems_service(),
                    campaign_page_records=resolved_campaign_page_records,
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
        campaign_page_records: list[object] | None = None,
        status_code: int = 200,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        resolved_campaign_page_records = (
            campaign_page_records
            if campaign_page_records is not None
            else list_visible_character_page_records(campaign_slug, campaign)
        )
        return (
            render_template(
                "character_retraining.html",
                campaign=campaign,
                character=present_character_detail(
                    campaign,
                    record,
                    include_player_notes_section=True,
                    systems_service=get_systems_service(),
                    campaign_page_records=resolved_campaign_page_records,
                ),
                retraining_context=retraining_context,
                active_nav="characters",
            ),
            status_code,
        )

    def character_sheet_return_href(campaign_slug: str, character_slug: str) -> str:
        if can_access_campaign_scope(campaign_slug, "characters"):
            return url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=character_slug,
            )
        if has_session_mode_access(campaign_slug, character_slug):
            return url_for(
                "campaign_session_character_view",
                campaign_slug=campaign_slug,
                character=character_slug,
            )
        return url_for(
            "character_read_view",
            campaign_slug=campaign_slug,
            character_slug=character_slug,
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
                level_up_back_href=character_sheet_return_href(campaign_slug, character_slug),
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

    def run_character_state_mutation(
        campaign_slug: str,
        character_slug: str,
        *,
        anchor: str,
        success_message: str,
        action,
    ):
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        inactive_session_redirect = ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor=anchor,
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect

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

        inactive_session_redirect = ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor=anchor,
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect

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
        if (
            combatant.character_slug not in get_owned_character_slugs(campaign_slug)
            and not can_manage_campaign_combat(campaign_slug)
        ):
            abort(403)

        record = get_character_repository().get_visible_character(campaign_slug, combatant.character_slug)
        if record is None:
            abort(404)

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            expected_revision = parse_expected_revision()
            action(record, expected_revision, user.id)
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            mutation_succeeded = True
            get_campaign_combat_service().mark_character_state_changed(
                campaign_slug,
                updated_by_user_id=user.id,
            )
            flash(success_message, "success")

        combat_return_view_raw = str(request.values.get("combat_view") or "").strip().lower()
        if is_async_request() or combat_return_view_raw in {"character", "combat", "dm", "status"}:
            return respond_to_campaign_combat_mutation(
                campaign_slug,
                mutation_succeeded=mutation_succeeded,
                anchor=anchor,
                fallback_combatant_id=combatant_id,
            )

        return redirect_to_campaign_combat_character(
            campaign_slug,
            combatant_id=combatant_id,
            anchor=anchor,
        )

    def run_combat_character_definition_mutation(
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
        if (
            combatant.character_slug not in get_owned_character_slugs(campaign_slug)
            and not can_manage_campaign_combat(campaign_slug)
        ):
            abort(403)

        record = get_character_repository().get_visible_character(campaign_slug, combatant.character_slug)
        if record is None:
            abort(404)

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            expected_revision = parse_expected_revision()
            result = action(record)
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
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
            config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / combatant.character_slug
            write_yaml(character_dir / "definition.yaml", definition.to_dict())
            write_yaml(character_dir / "import.yaml", import_metadata.to_dict())
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterEditValidationError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            mutation_succeeded = True
            flash(success_message, "success")

        return respond_to_campaign_combat_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor=anchor,
        )

    def build_campaign_session_page_context(
        campaign_slug: str,
        *,
        session_subpage: str = "session",
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        session_service = get_campaign_session_service()
        current_user = get_current_user()
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
                systems_entry = get_shared_pullable_session_systems_entry(
                    campaign_slug,
                    source_ref,
                    systems_service=get_systems_service(),
                    can_access_systems=can_access_campaign_scope(campaign_slug, "systems"),
                    can_access_systems_entry=lambda entry_slug: can_access_campaign_systems_entry(
                        campaign_slug,
                        entry_slug,
                    ),
                )
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
            live_messages = session_service.list_messages(
                active_session_record.id,
                viewer_user_id=int(current_user.id if current_user else 0) or None,
                can_manage_session=can_manage_session,
            )
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
        requested_session_subpage = str(session_subpage or "").strip().lower()
        session_shell_active_pane = (
            requested_session_subpage
            if requested_session_subpage in {"session", "character", "dm"}
            else "session"
        )
        normalized_session_subpage = normalize_session_subpage(session_subpage)
        session_poll_settings = build_session_poll_settings(normalized_session_subpage)
        session_player_poll_settings = build_session_poll_settings("session")
        session_dm_poll_settings = build_session_poll_settings("dm")
        session_live_revision = session_service.get_live_revision(campaign_slug)
        current_preferences = get_current_user_preferences()

        def _session_live_view_token(subpage: str) -> str:
            return build_shared_session_live_view_token(
                campaign_slug,
                subpage,
                session_chat_order=current_preferences.session_chat_order,
                can_manage_session=can_manage_session,
                can_post_session_messages=can_post_messages,
            )

        session_live_view_token = _session_live_view_token(normalized_session_subpage)
        session_player_live_view_token = _session_live_view_token("session")
        session_dm_live_view_token = _session_live_view_token("dm")
        accessible_session_character_records = list_session_accessible_character_records(campaign_slug)
        show_session_character_tab = bool(accessible_session_character_records)
        default_session_character_slug = get_default_session_character_slug(
            campaign_slug,
            accessible_records=accessible_session_character_records,
        )
        session_dm_passive_scores = present_session_dm_passive_score_rows(
            campaign,
            accessible_session_character_records,
            systems_service=get_systems_service(),
            campaign_page_records=list_visible_character_page_records(campaign.slug, campaign),
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
            "session_message_recipient_player_choices": build_session_message_recipient_player_choices(campaign_slug),
            "session_manager_state_token": build_session_manager_state_token(
                active_session_id=active_session_record.id if active_session_record is not None else None,
                staged_articles=staged_articles,
                revealed_articles=revealed_articles,
                session_logs=session_logs,
            ),
            "session_live_revision": session_live_revision,
            "session_live_view_token": session_live_view_token,
            "session_player_live_view_token": session_player_live_view_token,
            "session_dm_live_view_token": session_dm_live_view_token,
            "live_diagnostics_enabled": app.config["LIVE_DIAGNOSTICS"],
            "session_poll_active_interval_ms": session_poll_settings["active_interval_ms"],
            "session_poll_idle_interval_ms": session_poll_settings["idle_interval_ms"],
            "session_poll_idle_threshold_ms": session_poll_settings["idle_threshold_ms"],
            "session_player_poll_active_interval_ms": session_player_poll_settings["active_interval_ms"],
            "session_player_poll_idle_interval_ms": session_player_poll_settings["idle_interval_ms"],
            "session_player_poll_idle_threshold_ms": session_player_poll_settings["idle_threshold_ms"],
            "session_dm_poll_active_interval_ms": session_dm_poll_settings["active_interval_ms"],
            "session_dm_poll_idle_interval_ms": session_dm_poll_settings["idle_interval_ms"],
            "session_dm_poll_idle_threshold_ms": session_dm_poll_settings["idle_threshold_ms"],
            "session_subpage": normalized_session_subpage,
            "session_shell_active_pane": session_shell_active_pane,
            "session_dm_passive_scores": session_dm_passive_scores,
            "show_session_dm_passive_scores": is_dnd_5e_system(campaign.system),
            "session_character_panel_loaded": False,
            "show_session_character_tab": show_session_character_tab,
            "session_character_switch_href": (
                url_for(
                    "campaign_session_character_view",
                    campaign_slug=campaign.slug,
                    character=default_session_character_slug,
                )
                if show_session_character_tab
                else ""
            ),
            "session_character_fragment_href": (
                url_for(
                    "campaign_session_character_view",
                    campaign_slug=campaign.slug,
                    character=default_session_character_slug,
                    fragment="1",
                )
                if show_session_character_tab
                else ""
            ),
            "active_nav": "session",
        }

    def build_campaign_session_shell_context(
        campaign_slug: str,
        *,
        active_pane: str = "session",
        character_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        normalized_active_pane = str(active_pane or "").strip().lower()
        if normalized_active_pane not in {"session", "character", "dm"}:
            normalized_active_pane = "session"

        session_context = build_campaign_session_page_context(
            campaign_slug,
            session_subpage=(
                "dm"
                if normalized_active_pane == "dm"
                else "session"
            ),
        )
        session_context["session_shell_active_pane"] = normalized_active_pane
        if normalized_active_pane == "character":
            if character_context is None:
                character_context = build_campaign_session_character_page_context(campaign_slug)
            session_context.update(character_context)
            session_context["session_shell_active_pane"] = "character"
            session_context["session_character_panel_loaded"] = True
        return session_context

    def create_session_article_from_request(
        campaign_slug: str,
        *,
        created_by_user_id: int,
    ):
        session_service = get_campaign_session_service()
        article = None
        article_mode = normalize_session_article_form_mode(request.form.get("article_mode", "manual"))
        markdown_file = request.files.get("markdown_file")
        image_file = request.files.get("image_file")
        referenced_image_file = request.files.get("referenced_image_file")
        source_kind = ""

        try:
            if article_mode == "upload":
                markdown_filename = (markdown_file.filename or "").strip() if markdown_file is not None else ""
                markdown_upload = session_service.parse_article_markdown_upload(
                    filename=markdown_filename,
                    data_blob=(
                        read_bounded_upload(
                            markdown_file,
                            max_bytes=MAX_MARKDOWN_BYTES,
                            message="Session article markdown files must stay under 1 MB.",
                        )
                        if markdown_file is not None
                        else b""
                    ),
                )
                referenced_image_filename = (
                    (referenced_image_file.filename or "").strip() if referenced_image_file is not None else ""
                )
                if markdown_upload.image_reference and not referenced_image_filename:
                    raise CampaignSessionValidationError(
                        "This markdown file references an image. Upload the referenced image file too."
                    )
                referenced_image_upload = None
                if referenced_image_file is not None and referenced_image_filename:
                    referenced_image_upload = session_service.prepare_article_image_upload(
                        filename=referenced_image_filename,
                        media_type=referenced_image_file.mimetype,
                        data_blob=read_bounded_upload(
                            referenced_image_file,
                            max_bytes=MAX_INGRESS_FILE_BYTES,
                            message="Session article images must stay under 8 MB.",
                        ),
                        alt_text=markdown_upload.image_alt,
                        caption=markdown_upload.image_caption,
                    )
                article = session_service.create_article(
                    campaign_slug,
                    title=markdown_upload.title,
                    body_markdown=markdown_upload.body_markdown,
                    has_content_image=referenced_image_upload is not None,
                    created_by_user_id=created_by_user_id,
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
                        updated_by_user_id=created_by_user_id,
                    )
            elif article_mode == "wiki":
                campaign = load_campaign_context(campaign_slug)
                source_kind, source_ref = parse_session_article_source_ref(
                    request.form.get("source_ref", "") or request.form.get("wiki_page_ref", "")
                )
                if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
                    entry = get_shared_pullable_session_systems_entry(
                        campaign_slug,
                        source_ref,
                        systems_service=get_systems_service(),
                        can_access_systems=can_access_campaign_scope(campaign_slug, "systems"),
                        can_access_systems_entry=lambda entry_slug: can_access_campaign_systems_entry(
                            campaign_slug,
                            entry_slug,
                        ),
                    )
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
                        created_by_user_id=created_by_user_id,
                    )
                else:
                    page_record = get_shared_pullable_session_wiki_page_record(
                        campaign,
                        source_ref,
                        page_store=get_campaign_page_store(),
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
                                data_blob=read_bounded_file(
                                    image_path,
                                    max_bytes=MAX_INGRESS_FILE_BYTES,
                                    message="Wiki page images must stay under 8 MB.",
                                ),
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
                        created_by_user_id=created_by_user_id,
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
                            updated_by_user_id=created_by_user_id,
                        )
            else:
                image_filename = (image_file.filename or "").strip() if image_file is not None else ""
                manual_image_upload = None
                if image_file is not None and image_filename:
                    manual_image_upload = session_service.prepare_article_image_upload(
                        filename=image_filename,
                        media_type=image_file.mimetype,
                        data_blob=read_bounded_upload(
                            image_file,
                            max_bytes=MAX_INGRESS_FILE_BYTES,
                            message="Session article images must stay under 8 MB.",
                        ),
                        alt_text=request.form.get("image_alt", ""),
                        caption=request.form.get("image_caption", ""),
                    )
                article = session_service.create_article(
                    campaign_slug,
                    title=request.form.get("title", ""),
                    body_markdown=request.form.get("body_markdown", ""),
                    has_content_image=manual_image_upload is not None,
                    created_by_user_id=created_by_user_id,
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
                        updated_by_user_id=created_by_user_id,
                    )
        except CampaignSessionValidationError:
            if article is not None:
                try:
                    session_service.delete_article(campaign_slug, article.id, updated_by_user_id=created_by_user_id)
                except CampaignSessionValidationError:
                    pass
            raise

        return article, article_mode, source_kind

    def update_session_article_from_request(
        campaign_slug: str,
        article_id: int,
        *,
        updated_by_user_id: int,
    ):
        session_service = get_campaign_session_service()
        image_file = request.files.get("image_file")
        image_filename = (image_file.filename or "").strip() if image_file is not None else ""
        image_alt = request.form.get("image_alt", "")
        image_caption = request.form.get("image_caption", "")
        image_upload = None
        if image_file is not None and image_filename:
            image_upload = session_service.prepare_article_image_upload(
                filename=image_filename,
                media_type=image_file.mimetype,
                data_blob=read_bounded_upload(
                    image_file,
                    max_bytes=MAX_INGRESS_FILE_BYTES,
                    message="Session article images must stay under 8 MB.",
                ),
                alt_text=image_alt,
                caption=image_caption,
            )
        existing_image = session_service.get_article_image(campaign_slug, article_id)
        has_image = image_upload is not None or existing_image is not None

        updated_article = session_service.update_article(
            campaign_slug,
            article_id,
            title=request.form.get("title", ""),
            body_markdown=request.form.get("body_markdown", ""),
            has_content_image=has_image,
            updated_by_user_id=updated_by_user_id,
        )
        if image_upload is not None:
            session_service.attach_article_image(
                campaign_slug,
                article_id,
                filename=image_upload.filename,
                media_type=image_upload.media_type,
                data_blob=image_upload.data_blob,
                alt_text=image_upload.alt_text,
                caption=image_upload.caption,
                updated_by_user_id=updated_by_user_id,
            )
        elif existing_image is not None:
            session_service.update_article_image_metadata(
                campaign_slug,
                article_id,
                alt_text=image_alt,
                caption=image_caption,
                updated_by_user_id=updated_by_user_id,
            )
        return updated_article

    def build_campaign_session_character_page_context(
        campaign_slug: str,
        *,
        selected_character_slug: str | None = None,
        requested_subpage: str | None = None,
        requested_confirm_rest: str | None = None,
        notes_draft: str | None = None,
        physical_description_draft: str | None = None,
        background_draft: str | None = None,
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        dnd5e_spellcasting_tools_supported = campaign_supports_dnd5e_character_spellcasting_tools(campaign)
        native_character_tools_supported = campaign_supports_native_character_tools(campaign)
        session_service = get_campaign_session_service()
        can_manage_session = can_manage_campaign_session(campaign_slug)
        can_manage_combat = can_manage_campaign_combat(campaign_slug)
        accessible_records = list_session_accessible_character_records(campaign_slug)
        accessible_records_by_slug = {
            record.definition.character_slug: record for record in accessible_records
        }

        active_session_record = session_service.get_active_session(campaign_slug)
        active_session = None
        if active_session_record is not None:
            user = get_current_user()
            live_messages = session_service.list_messages(
                active_session_record.id,
                viewer_user_id=int(user.id if user else 0) or None,
                can_manage_session=can_manage_session,
            )
            active_session = present_session_record(
                active_session_record,
                message_count=len(live_messages),
            )

        close_requested = (
            selected_character_slug is None
            and can_manage_session
            and request.args.get("closed") == "1"
        )
        requested_character_slug = (
            str(selected_character_slug).strip()
            if selected_character_slug is not None
            else request.args.get("character", "").strip()
        )
        if requested_character_slug and requested_character_slug not in accessible_records_by_slug:
            abort(403)
        selected_character_slug = (
            ""
            if close_requested
            else requested_character_slug
            or (
                get_default_session_character_slug(
                    campaign_slug,
                    accessible_records=accessible_records,
                )
                or ""
            )
        )

        session_character_cards = []
        for card in present_character_roster(accessible_records):
            card_slug = str(card.get("slug") or "").strip()
            session_character_cards.append(
                {
                    **card,
                    "is_selected": card_slug == selected_character_slug,
                    "href": url_for(
                        "campaign_session_character_view",
                        campaign_slug=campaign.slug,
                        character=card_slug,
                    ),
                }
            )

        character = None
        character_subpage = "overview"
        character_subpages = []
        equipment_state_manager = None
        spell_manager = None
        rest_preview = None
        session_character_editing_enabled = False
        can_view_full_character_sheet = False
        full_character_sheet_url = ""
        session_surface_return_url = ""
        session_surface_short_rest_url = ""
        session_surface_long_rest_url = ""
        session_personal_edit_block_message = ""
        session_personal_edit_block_href = ""
        session_personal_edit_block_action_label = ""
        session_character_empty_state_title = ""
        session_character_empty_state_message = ""

        if selected_character_slug:
            record = accessible_records_by_slug[selected_character_slug]
            character_campaign_page_records = list_visible_character_page_records(campaign_slug, campaign)
            character_item_catalog = build_character_item_catalog(campaign_slug)
            character_spell_catalog = (
                _build_spell_catalog(
                    _list_campaign_enabled_entries(
                        app.extensions["systems_service"],
                        campaign_slug,
                        "spell",
                    )
                )
                if dnd5e_spellcasting_tools_supported
                else {}
            )
            character = present_character_detail(
                campaign,
                record,
                include_player_notes_section=True,
                systems_service=get_systems_service(),
                campaign_page_records=character_campaign_page_records,
            )
            if notes_draft is not None:
                character["player_notes_markdown"] = notes_draft
            if physical_description_draft is not None:
                character["physical_description_markdown"] = physical_description_draft
            if background_draft is not None:
                character["personal_background_markdown"] = background_draft
            character["portrait"] = build_character_portrait_context(campaign, record.definition)
            spell_manager = None
            if dnd5e_spellcasting_tools_supported:
                spell_manager = build_character_spell_manager_context(
                    campaign_slug,
                    campaign,
                    record,
                    spell_catalog=character_spell_catalog,
                )
                if not character.get("spellcasting") and spell_manager is not None:
                    spellcasting_placeholder = build_character_spellcasting_placeholder(spell_manager)
                    if spellcasting_placeholder is not None:
                        character["spellcasting"] = spellcasting_placeholder
            else:
                character.pop("spellcasting", None)
            include_spellcasting_subpage = bool(character.get("spellcasting"))
            xianxia_read_context = (
                dict(character.get("xianxia_read") or {})
                if isinstance(character.get("xianxia_read"), dict)
                else None
            )
            character_subpage = normalize_session_character_subpage(
                requested_subpage if requested_subpage is not None else request.args.get("page", ""),
                include_spellcasting=include_spellcasting_subpage,
                xianxia_read=xianxia_read_context,
            )
            session_character_editing_enabled = bool(
                active_session_record is not None
                and has_session_mode_access(campaign_slug, selected_character_slug)
            )
            confirm_rest = (
                str(requested_confirm_rest).strip().lower()
                if requested_confirm_rest is not None
                else request.args.get("confirm_rest", "").strip().lower()
            )
            if session_character_editing_enabled and confirm_rest in {"short", "long"}:
                rest_preview = get_character_state_service().preview_rest(record, confirm_rest)
            equipment_state_manager = build_character_equipment_state_context(
                campaign_slug,
                campaign,
                record,
                item_catalog=character_item_catalog,
            )
            character_subpages = [
                {
                    "slug": str(section.get("slug") or ""),
                    "label": str(section.get("label") or ""),
                    "count": int(section.get("count") or 0),
                    "href": url_for(
                        "campaign_session_character_view",
                        campaign_slug=campaign.slug,
                        character=selected_character_slug,
                        page=section.get("slug"),
                    ),
                    "is_active": str(section.get("slug") or "") == character_subpage,
                }
                for section in build_session_character_sections(
                    character,
                    equipment_state_manager=equipment_state_manager,
                    include_spellcasting=include_spellcasting_subpage,
                    session_character_subpage_labels=get_session_character_subpage_labels(
                        include_spellcasting=include_spellcasting_subpage,
                        xianxia_read=xianxia_read_context,
                    ),
                )
            ]
            can_view_full_character_sheet = bool(
                selected_character_slug and can_access_campaign_scope(campaign_slug, "characters")
            )
            full_character_sheet_url = (
                build_session_character_read_view_url(
                    campaign.slug,
                    selected_character_slug,
                    character_subpage,
                    xianxia_read=xianxia_read_context,
                )
                if can_view_full_character_sheet
                else ""
            )
            session_surface_return_url = url_for(
                "campaign_session_character_view",
                campaign_slug=campaign.slug,
                character=selected_character_slug,
                page=character_subpage,
            )
            session_surface_short_rest_url = url_for(
                "campaign_session_character_view",
                campaign_slug=campaign.slug,
                character=selected_character_slug,
                page=character_subpage,
                confirm_rest="short",
            )
            session_surface_long_rest_url = url_for(
                "campaign_session_character_view",
                campaign_slug=campaign.slug,
                character=selected_character_slug,
                page=character_subpage,
                confirm_rest="long",
            )
            if session_character_editing_enabled:
                if native_character_tools_supported:
                    session_personal_edit_block_message = (
                        SESSION_CHARACTER_ADVANCED_PERSONAL_EDIT_BLOCK_MESSAGE
                    )
                    session_personal_edit_block_href = url_for(
                        "character_edit_view",
                        campaign_slug=campaign.slug,
                        character_slug=selected_character_slug,
                    )
                    session_personal_edit_block_action_label = "Open Advanced Editor"
                else:
                    session_personal_edit_block_message = SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE
                    session_personal_edit_block_href = (
                        build_session_character_read_view_url(
                            campaign.slug,
                            selected_character_slug,
                            "personal",
                            xianxia_read=xianxia_read_context,
                        )
                        if can_view_full_character_sheet
                        else ""
                    )
                    session_personal_edit_block_action_label = "Open full character page"
        else:
            (
                session_character_empty_state_title,
                session_character_empty_state_message,
            ) = build_session_character_empty_state(
                campaign_slug,
                can_manage_session=can_manage_session,
                accessible_records=accessible_records,
            )

        return {
            "campaign": campaign,
            "active_session": active_session,
            "active_session_id": active_session_record.id if active_session_record is not None else None,
            "can_manage_session": can_manage_session,
            "session_subpage": "character",
            "show_session_character_tab": bool(accessible_records),
            "session_character_switch_href": (
                url_for(
                    "campaign_session_character_view",
                    campaign_slug=campaign.slug,
                    character=selected_character_slug or None,
                    page=character_subpage if selected_character_slug else None,
                )
                if accessible_records
                else ""
            ),
            "session_character_fragment_href": (
                url_for(
                    "campaign_session_character_view",
                    campaign_slug=campaign.slug,
                    character=selected_character_slug or None,
                    page=character_subpage if selected_character_slug else None,
                    fragment="1",
                )
                if accessible_records
                else ""
            ),
            "session_character_cards": session_character_cards,
            "session_character_can_close": bool(can_manage_session and selected_character_slug),
            "session_character_close_href": (
                url_for(
                    "campaign_session_character_view",
                    campaign_slug=campaign.slug,
                    closed="1",
                )
                if can_manage_session and selected_character_slug
                else ""
            ),
            "session_character_empty_state_title": session_character_empty_state_title,
            "session_character_empty_state_message": session_character_empty_state_message,
            "character": character,
            "character_subpage": character_subpage,
            "character_subpages": character_subpages,
            "equipment_state_manager": equipment_state_manager,
            "spell_manager": spell_manager,
            "inventory_manager": None,
            "character_controls": None,
            "can_use_session_mode": session_character_editing_enabled,
            "is_session_mode": session_character_editing_enabled,
            "rest_preview": rest_preview,
            "session_character_editing_enabled": session_character_editing_enabled,
            "session_personal_edit_block_message": session_personal_edit_block_message,
            "session_personal_edit_block_href": session_personal_edit_block_href,
            "session_personal_edit_block_action_label": session_personal_edit_block_action_label,
            "session_return_view": "session-character",
            "session_surface_return_url": session_surface_return_url,
            "session_surface_short_rest_url": session_surface_short_rest_url,
            "session_surface_long_rest_url": session_surface_long_rest_url,
            "can_view_full_character_sheet": can_view_full_character_sheet,
            "full_character_sheet_url": full_character_sheet_url,
            "active_nav": "session",
        }

    def render_session_character_page(
        campaign_slug: str,
        character_slug: str,
        *,
        notes_draft: str | None = None,
        physical_description_draft: str | None = None,
        background_draft: str | None = None,
        status_code: int = 200,
    ):
        context = build_campaign_session_character_page_context(
            campaign_slug,
            selected_character_slug=character_slug,
            requested_subpage=request.values.get("page", ""),
            requested_confirm_rest=request.values.get("confirm_rest", ""),
            notes_draft=notes_draft,
            physical_description_draft=physical_description_draft,
            background_draft=background_draft,
        )
        shell_context = build_campaign_session_shell_context(
            campaign_slug,
            active_pane="character",
            character_context=context,
        )
        return render_template("session_character.html", **shell_context), status_code

    def resolve_combat_character_target(
        tracker_view: dict[str, object],
        allowed_target_rows: list[dict[str, object]],
        *,
        explicit_combatant_id_raw: str = "",
        explicit_character_slug: str = "",
        strict_explicit: bool = False,
    ) -> dict[str, object] | None:
        selected_target = None
        normalized_combatant_id = explicit_combatant_id_raw.strip()
        normalized_character_slug = explicit_character_slug.strip()

        if normalized_combatant_id:
            try:
                explicit_combatant_id = int(normalized_combatant_id)
            except ValueError:
                if strict_explicit:
                    abort(403)
                explicit_combatant_id = None
            if explicit_combatant_id is not None:
                selected_target = next(
                    (
                        row
                        for row in allowed_target_rows
                        if row["combatant_record"].id == explicit_combatant_id
                    ),
                    None,
                )
                if selected_target is None and strict_explicit:
                    abort(403)
        elif normalized_character_slug:
            selected_target = next(
                (
                    row
                    for row in allowed_target_rows
                    if row["record"].definition.character_slug == normalized_character_slug
                ),
                None,
            )
            if selected_target is None and strict_explicit:
                abort(403)

        if selected_target is None:
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

        return selected_target

    def _combat_npc_heading_text(value: object) -> str:
        return " ".join(
            unescape(COMBAT_NPC_HTML_TAG_PATTERN.sub("", str(value or ""))).split()
        )

    def _combat_npc_heading_section(value: object) -> tuple[str, bool]:
        normalized = normalize_lookup(_combat_npc_heading_text(value))
        if not normalized:
            return "", False
        section_slug = COMBAT_NPC_WORKSPACE_SECTION_HEADING_ALIASES.get(normalized, "")
        if section_slug:
            return section_slug, False
        entry_section_slug = COMBAT_NPC_WORKSPACE_SECTION_ENTRY_ALIASES.get(normalized, "")
        if entry_section_slug:
            return entry_section_slug, True
        heading_text = _combat_npc_heading_text(value)
        match = COMBAT_NPC_WORKSPACE_ENTRY_HEADING_WITH_SUFFIX_PATTERN.match(heading_text)
        if match:
            normalized_without_suffix = normalize_lookup(match.group("name"))
            entry_section_slug = COMBAT_NPC_WORKSPACE_SECTION_ENTRY_ALIASES.get(
                normalized_without_suffix,
                "",
            )
            if entry_section_slug:
                return entry_section_slug, True
        return "", False

    def _combat_npc_format_bonus(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return ""
            if re.fullmatch(r"[+-]?\d+", normalized):
                return format_signed(int(normalized))
            return normalized
        if isinstance(value, (int, float)):
            return format_signed(int(value))
        return str(value).strip()

    def _combat_npc_format_named_value(name: object) -> str:
        raw_name = str(name or "").strip().replace("_", " ")
        if not raw_name:
            return ""
        normalized = normalize_lookup(raw_name)
        if normalized in COMBAT_NPC_ABILITY_LABELS:
            return COMBAT_NPC_ABILITY_LABELS[normalized]
        return raw_name.title()

    def _combat_npc_extract_statblock_line(markdown_text: str, label: str) -> str:
        pattern = re.compile(
            rf"(?im)^\s*\*{{0,2}}{re.escape(label)}\*{{0,2}}\s*:?\s*(?P<value>.+?)\s*$"
        )
        match = pattern.search(markdown_text or "")
        return str(match.group("value") if match is not None else "").strip()

    def _combat_npc_parse_named_bonus_items(markdown_text: str, label: str) -> list[dict[str, str]]:
        line = _combat_npc_extract_statblock_line(markdown_text, label)
        if not line:
            return []
        entries: list[dict[str, str]] = []
        for match in re.finditer(r"(?P<name>[A-Za-z][A-Za-z' /()-]*?)\s*(?P<bonus>[+-]\d+)\b", line):
            name = _combat_npc_format_named_value(match.group("name"))
            bonus = _combat_npc_format_bonus(match.group("bonus"))
            if not name or not bonus:
                continue
            entries.append({"name": name, "bonus": bonus})
        return entries

    def _combat_npc_build_ability_rows(
        raw_scores: dict[str, object],
        *,
        raw_saves: dict[str, object] | None = None,
    ) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        save_lookup = raw_saves or {}
        for ability_key in COMBAT_NPC_ABILITY_ORDER:
            raw_score = raw_scores.get(ability_key)
            try:
                score = int(raw_score)
            except (TypeError, ValueError):
                continue
            modifier = (score - 10) // 2
            save_bonus = _combat_npc_format_bonus(save_lookup.get(ability_key))
            if not save_bonus:
                save_bonus = format_signed(modifier)
            rows.append(
                {
                    "abbr": ability_key.upper(),
                    "name": COMBAT_NPC_ABILITY_LABELS[ability_key],
                    "score": str(score),
                    "modifier": format_signed(modifier),
                    "save_bonus": save_bonus,
                }
            )
        return rows

    def _combat_npc_parse_statblock_abilities(markdown_text: str) -> dict[str, int]:
        score_lookup: dict[str, int] = {}
        for match in COMBAT_NPC_STATBLOCK_ABILITY_PATTERN.finditer(markdown_text or ""):
            ability_key = normalize_lookup(match.group("key"))
            if ability_key not in COMBAT_NPC_ABILITY_LABELS:
                continue
            if ability_key in score_lookup:
                continue
            score_lookup[ability_key] = int(match.group("score"))
        return score_lookup

    def _combat_npc_parse_html_blocks_by_section(body_html: str) -> dict[str, list[dict[str, str]]]:
        section_blocks = {slug: [] for slug in COMBAT_NPC_WORKSPACE_SECTION_ORDER}
        normalized_html = str(body_html or "").strip()
        if not normalized_html:
            return section_blocks

        heading_matches = list(COMBAT_NPC_HTML_HEADING_PATTERN.finditer(normalized_html))
        if not heading_matches:
            section_blocks["actions"].append({"title": "", "body_html": normalized_html})
            return section_blocks

        active_slug = ""
        for index, heading_match in enumerate(heading_matches):
            next_start = (
                heading_matches[index + 1].start()
                if index + 1 < len(heading_matches)
                else len(normalized_html)
            )
            title = _combat_npc_heading_text(heading_match.group("title"))
            section_slug, preserve_title = _combat_npc_heading_section(heading_match.group("title"))
            body_fragment = normalized_html[heading_match.end() : next_start].strip()
            if section_slug:
                active_slug = section_slug
                if body_fragment:
                    section_blocks[section_slug].append(
                        {
                            "title": title if preserve_title else "",
                            "body_html": body_fragment,
                        }
                    )
                continue
            target_slug = active_slug or "actions"
            if not title and not body_fragment:
                continue
            section_blocks[target_slug].append(
                {
                    "title": title,
                    "body_html": body_fragment,
                }
            )
        return section_blocks

    def _combat_npc_build_systems_abilities_skills_payload(
        metadata: dict[str, object],
    ) -> dict[str, object]:
        raw_abilities_value = metadata.get("abilities")
        raw_saving_throws_value = metadata.get("saving_throws")
        raw_skills_value = metadata.get("skills")
        raw_abilities = dict(raw_abilities_value) if isinstance(raw_abilities_value, dict) else {}
        raw_saving_throws = (
            dict(raw_saving_throws_value) if isinstance(raw_saving_throws_value, dict) else {}
        )
        raw_skills = dict(raw_skills_value) if isinstance(raw_skills_value, dict) else {}
        skills = [
            {
                "name": _combat_npc_format_named_value(skill_name),
                "bonus": _combat_npc_format_bonus(skill_bonus),
            }
            for skill_name, skill_bonus in raw_skills.items()
            if _combat_npc_format_named_value(skill_name)
            and _combat_npc_format_bonus(skill_bonus)
        ]
        skills.sort(key=lambda item: item["name"])
        supplemental_rows = []
        for label, raw_value in (
            ("Senses", metadata.get("senses")),
            ("Languages", metadata.get("languages")),
            ("Challenge", metadata.get("cr")),
        ):
            if isinstance(raw_value, list):
                value = ", ".join(str(item).strip() for item in raw_value if str(item).strip())
            elif isinstance(raw_value, dict):
                challenge_rating = str(raw_value.get("cr") or "").strip()
                challenge_xp = str(raw_value.get("xp") or "").strip()
                if challenge_rating and challenge_xp:
                    value = f"{challenge_rating} ({challenge_xp} XP)"
                else:
                    value = challenge_rating or challenge_xp
            else:
                value = str(raw_value or "").strip()
            if value:
                supplemental_rows.append({"label": label, "value": value})
        return {
            "abilities": _combat_npc_build_ability_rows(
                raw_abilities,
                raw_saves=raw_saving_throws,
            ),
            "skills": skills,
            "supplemental_rows": supplemental_rows,
            "suppress_html_blocks": True,
        }

    def _combat_npc_build_statblock_abilities_skills_payload(
        markdown_text: str,
    ) -> dict[str, object]:
        saving_throws = _combat_npc_parse_named_bonus_items(markdown_text, "Saving Throws")
        save_lookup = {
            normalize_lookup(entry["name"]): entry["bonus"]
            for entry in saving_throws
            if entry.get("name") and entry.get("bonus")
        }
        skills = _combat_npc_parse_named_bonus_items(markdown_text, "Skills")
        supplemental_rows = []
        for label in ("Senses", "Languages", "Challenge"):
            value = _combat_npc_extract_statblock_line(markdown_text, label)
            if value:
                supplemental_rows.append({"label": label, "value": value})
        return {
            "abilities": _combat_npc_build_ability_rows(
                _combat_npc_parse_statblock_abilities(markdown_text),
                raw_saves=save_lookup,
            ),
            "skills": skills,
            "supplemental_rows": supplemental_rows,
            "suppress_html_blocks": False,
        }

    def build_combat_npc_workspace_sections(
        *,
        body_html: str,
        abilities_skills_payload: dict[str, object] | None = None,
    ) -> tuple[list[dict[str, object]], str]:
        parsed_blocks = _combat_npc_parse_html_blocks_by_section(body_html)
        abilities_payload = dict(abilities_skills_payload or {})
        abilities = [dict(item or {}) for item in list(abilities_payload.get("abilities") or [])]
        skills = [dict(item or {}) for item in list(abilities_payload.get("skills") or [])]
        supplemental_rows = [
            dict(item or {}) for item in list(abilities_payload.get("supplemental_rows") or [])
        ]
        suppress_html_blocks = bool(abilities_payload.get("suppress_html_blocks"))
        sections: list[dict[str, object]] = []
        for slug in COMBAT_NPC_WORKSPACE_SECTION_ORDER:
            blocks = [dict(item or {}) for item in list(parsed_blocks.get(slug) or [])]
            section_payload: dict[str, object] = {
                "slug": slug,
                "label": COMBAT_NPC_WORKSPACE_SECTION_LABELS[slug],
                "count": len(blocks),
                "has_content": bool(blocks),
                "entry_blocks": blocks,
                "empty_message": COMBAT_NPC_WORKSPACE_SECTION_EMPTY_MESSAGES[slug],
            }
            if slug == "abilities_skills":
                section_payload.update(
                    {
                        "abilities": abilities,
                        "skills": skills,
                        "supplemental_rows": supplemental_rows,
                        "suppress_html_blocks": suppress_html_blocks,
                    }
                )
                section_payload["count"] = (
                    len(skills)
                    or len(abilities)
                    or len(supplemental_rows)
                    or len(blocks)
                )
                section_payload["has_content"] = bool(
                    abilities or skills or supplemental_rows or blocks
                )
            sections.append(section_payload)

        sections = [section for section in sections if section["has_content"]]
        default_section = next((section["slug"] for section in sections), "")
        for section in sections:
            section["is_default"] = section["slug"] == default_section
        return sections, default_section

    def build_combat_character_detail_context(campaign_slug: str, campaign, record) -> dict[str, object]:
        campaign_page_records = list_visible_character_page_records(campaign_slug, campaign)
        item_catalog = build_character_item_catalog(campaign_slug)
        character_detail = present_character_detail(
            campaign,
            record,
            include_player_notes_section=False,
            systems_service=get_systems_service(),
            campaign_page_records=campaign_page_records,
        )
        equipment_state_manager = build_character_equipment_state_context(
            campaign_slug,
            campaign,
            record,
            item_catalog=item_catalog,
            campaign_page_records=campaign_page_records,
        )
        workspace_sections, workspace_default_section = build_combat_character_workspace_sections(
            character_detail,
            equipment_state_manager,
        )
        overview_stats = [
            stat
            for stat in list(character_detail.get("overview_stats") or [])
            if stat.get("label") not in {"Current HP", "Temp HP"}
        ]
        selected_character_slug = record.definition.character_slug
        combat_session_relationship_available = False
        combat_session_character_url = ""
        combat_session_page_url = ""
        if (
            get_campaign_session_service().get_active_session(campaign_slug) is not None
            and can_access_session_character_surface(campaign_slug, selected_character_slug)
        ):
            combat_session_relationship_available = True
            combat_session_character_url = url_for(
                "campaign_session_character_view",
                campaign_slug=campaign.slug,
                character=selected_character_slug,
            )
            combat_session_page_url = url_for(
                "campaign_session_view",
                campaign_slug=campaign.slug,
            )
        return {
            "selected_combat_character": character_detail,
            "selected_combat_overview_stats": overview_stats,
            "combat_equipment_state_manager": equipment_state_manager,
            "combat_workspace_sections": workspace_sections,
            "combat_workspace_default_section": workspace_default_section,
            "combat_session_relationship_available": combat_session_relationship_available,
            "combat_session_character_url": combat_session_character_url,
            "combat_session_page_url": combat_session_page_url,
            "combat_and_session_combat_scope": COMBAT_AND_SESSION_COMBAT_SCOPE,
            "combat_and_session_session_scope": COMBAT_AND_SESSION_SESSION_SCOPE,
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
        combat_dm_view: str | None = None,
        include_player_workspace_detail: bool = True,
    ) -> dict[str, object]:
        requested_combatant_id = (
            selected_combatant_id
            if selected_combatant_id is not None
            else parse_requested_combatant_id()
        )
        normalized_combat_dm_view = (
            normalize_combat_dm_view(combat_dm_view or request.values.get("view", ""))
            if combat_subpage == "dm"
            else "status"
        )
        campaign = load_campaign_context(campaign_slug)
        can_manage_combat = can_manage_campaign_combat(campaign_slug)
        combat_system_supported = supports_combat_tracker(campaign.system)
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
                combat_service.list_resource_counters_by_combatant(campaign_slug),
                combat_service.list_resource_notes_by_combatant(campaign_slug),
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
        accessible_combat_character_rows = list_accessible_combat_character_rows(
            combatants,
            tracker_view,
            character_records_by_slug,
            campaign_slug=campaign_slug,
            can_manage_combat=can_manage_combat,
        )
        show_player_combat_workspace = False
        combat_workspace_targets: list[dict[str, object]] = []
        combat_character_state_token = ""
        can_edit_combat_character_state = False
        can_edit_combat_equipment_state = False
        player_workspace_detail_context: dict[str, object] = {}
        if combat_subpage == "combat" and not can_manage_combat and accessible_combat_character_rows:
            selected_target = resolve_combat_character_target(
                tracker_view,
                accessible_combat_character_rows,
                explicit_combatant_id_raw=request.args.get("combatant", ""),
                strict_explicit=False,
            )
            if selected_target is not None:
                selected_combatant_record = selected_target["combatant_record"]
                selected_combatant = selected_target["combatant"]
                selected_combatant_id = selected_combatant_record.id
                requested_combatant_id = selected_combatant_id
                show_player_combat_workspace = True
                can_edit_combat_character_state = True
                can_edit_combat_equipment_state = True
                combat_character_state_token = build_selected_combatant_state_token(
                    tracker_view,
                    selected_combatant,
                )
                if include_player_workspace_detail:
                    player_workspace_detail_context = build_combat_character_detail_context(
                        campaign_slug,
                        campaign,
                        selected_target["record"],
                    )
                combat_workspace_targets = [
                    {
                        "combatant_id": row["combatant_record"].id,
                        "character_slug": row["record"].definition.character_slug,
                        "name": row["combatant"]["name"],
                        "subtitle": row["combatant"]["subtitle"],
                        "href": url_for(
                            "campaign_combat_view",
                            campaign_slug=campaign.slug,
                            combatant=row["combatant_record"].id,
                        ),
                        "is_active": row["combatant_record"].id == selected_combatant_id,
                    }
                    for row in accessible_combat_character_rows
                ]
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
        combat_live_view_token = build_shared_combat_live_view_token(
            campaign_slug,
            combat_subpage,
            selected_combatant_id=requested_combatant_id,
            combat_dm_view=normalized_combat_dm_view,
            can_manage_combat=can_manage_combat,
            owned_character_slugs=get_owned_character_slugs(campaign_slug),
            normalize_combat_dm_view=normalize_combat_dm_view,
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

        context = {
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
            "combat_dm_view": normalized_combat_dm_view if combat_subpage == "dm" else "status",
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
            "show_player_combat_workspace": show_player_combat_workspace,
            "combat_workspace_targets": combat_workspace_targets,
            "combat_character_state_token": combat_character_state_token,
            "can_edit_combat_character_state": can_edit_combat_character_state,
            "can_edit_combat_equipment_state": can_edit_combat_equipment_state,
            "active_nav": "combat",
            "_combatant_records": combatants,
            "_combat_conditions_by_combatant": conditions_by_combatant,
            "_combat_character_records_by_slug": character_records_by_slug,
            "_selected_combatant_record": selected_combatant_record,
        }
        context.update(player_workspace_detail_context)
        if combat_subpage == "dm":
            resolved_selected_combatant_id = context["selected_combatant_id"]
            status_dm_route_values = build_combat_route_values(
                campaign_slug,
                selected_combatant_id=resolved_selected_combatant_id,
            )
            controls_dm_route_values = dict(status_dm_route_values)
            controls_dm_route_values["view"] = "controls"
            context["combat_dm_view_status_url"] = url_for(
                "campaign_combat_dm_view",
                **status_dm_route_values,
            )
            context["combat_dm_view_controls_url"] = url_for(
                "campaign_combat_dm_view",
                **controls_dm_route_values,
            )
            dm_surface_urls = build_combat_surface_urls(
                campaign_slug,
                combat_subpage="dm",
                selected_combatant_id=resolved_selected_combatant_id,
                combat_dm_view=normalized_combat_dm_view,
            )
            context["combat_dm_live_url"] = dm_surface_urls["live_url"]
        return context

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
        selected_target = resolve_combat_character_target(
            tracker_view,
            allowed_target_rows,
            explicit_combatant_id_raw=request.args.get("combatant", ""),
            explicit_character_slug=request.args.get("character", ""),
            strict_explicit=True,
        )

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
                "can_edit_combat_equipment_state": selected_target is not None,
                "combat_character_state_token": build_selected_combatant_state_token(
                    tracker_view,
                    selected_combatant,
                ),
            }
        )
        context.update(character_detail_context)
        return context

    def require_explicit_combat_character_target_access(campaign_slug: str) -> None:
        explicit_combatant_id_raw = request.args.get("combatant", "").strip()
        explicit_character_slug = request.args.get("character", "").strip()
        if not explicit_combatant_id_raw and not explicit_character_slug:
            return
        if can_manage_campaign_combat(campaign_slug):
            return

        owned_character_slugs = get_owned_character_slugs(campaign_slug)
        combat_service = get_campaign_combat_service()
        if explicit_combatant_id_raw:
            try:
                explicit_combatant_id = int(explicit_combatant_id_raw)
            except ValueError:
                abort(403)
            combatant = combat_service.get_combatant(campaign_slug, explicit_combatant_id)
            character_slug = (
                combatant.character_slug
                if combatant is not None and combatant.is_player_character
                else None
            )
        else:
            character_slug = explicit_character_slug
            combatant = next(
                (
                    candidate
                    for candidate in combat_service.list_combatants(
                        campaign_slug,
                        sync_player_character_snapshots=False,
                    )
                    if candidate.is_player_character and candidate.character_slug == character_slug
                ),
                None,
            )

        if (
            combatant is None
            or not character_slug
            or character_slug not in owned_character_slugs
            or get_character_repository().get_visible_character(campaign_slug, character_slug) is None
        ):
            abort(403)

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
            body_html = render_campaign_markdown(campaign, statblock.body_markdown)
            workspace_sections, workspace_default_section = build_combat_npc_workspace_sections(
                body_html=body_html,
                abilities_skills_payload=_combat_npc_build_statblock_abilities_skills_payload(
                    statblock.body_markdown
                ),
            )
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
                "body_html": body_html,
                "workspace_sections": workspace_sections,
                "workspace_default_section": workspace_default_section,
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
            body_html = str(systems_entry.rendered_html or "").strip()
            workspace_sections, workspace_default_section = build_combat_npc_workspace_sections(
                body_html=body_html,
                abilities_skills_payload=_combat_npc_build_systems_abilities_skills_payload(
                    dict(systems_entry.metadata or {})
                ),
            )
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
                "body_html": body_html,
                "workspace_sections": workspace_sections,
                "workspace_default_section": workspace_default_section,
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
        selected_combatant_id: int | None = None,
        sync_player_character_snapshots: bool = True,
        strict_selected_combatant: bool = True,
    ) -> dict[str, object]:
        if not can_manage_campaign_combat(campaign_slug):
            abort(403)

        explicit_combatant_id = (
            selected_combatant_id
            if selected_combatant_id is not None
            else parse_requested_combatant_id(strict=strict_selected_combatant)
        )
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
            strict_explicit=explicit_combatant_id is not None and strict_selected_combatant,
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
                "can_edit_combat_character_state": bool(
                    selected_combatant_record is not None
                    and selected_combatant_record.is_player_character
                    and selected_combatant_record.character_slug
                ),
                "can_edit_combat_equipment_state": bool(
                    selected_combatant_record is not None
                    and selected_combatant_record.is_player_character
                    and selected_combatant_record.character_slug
                ),
            }
        )
        context.update(source_context)
        return context

    def build_campaign_combat_dm_status_context(
        campaign_slug: str,
        *,
        selected_combatant_id: int | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        context = build_campaign_combat_status_context(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
            sync_player_character_snapshots=sync_player_character_snapshots,
            strict_selected_combatant=False,
        )
        resolved_selected_combatant_id = context["selected_combatant_id"]
        selected_combatant = context["selected_combatant"]
        selected_character_combatant_id = (
            resolved_selected_combatant_id
            if isinstance(selected_combatant, dict)
            and selected_combatant.get("can_open_character_page")
            else None
        )
        selected_character_slug = (
            str(selected_combatant.get("character_slug") or "")
            if isinstance(selected_combatant, dict)
            and selected_combatant.get("can_open_character_page")
            else None
        )
        route_values = build_combat_route_values(
            campaign_slug,
            selected_combatant_id=resolved_selected_combatant_id,
        )
        controls_route_values = dict(route_values)
        controls_route_values["view"] = "controls"
        dm_live_urls = build_combat_surface_urls(
            campaign_slug,
            combat_subpage="dm",
            selected_combatant_id=resolved_selected_combatant_id,
            combat_dm_view="status",
        )
        dm_poll_settings = build_combat_poll_settings("dm")
        context.update(
            {
                "combat_subpage": "dm",
                "combat_dm_view": "status",
                "combat_return_view": "dm",
                "combat_summary_compact": True,
                "combat_summary_show_focus_picker": False,
                "combat_dm_view_status_url": url_for(
                    "campaign_combat_dm_view",
                    **route_values,
                ),
                "combat_dm_view_controls_url": url_for(
                    "campaign_combat_dm_view",
                    **controls_route_values,
                ),
                "combat_dm_live_url": dm_live_urls["live_url"],
                "combat_poll_active_interval_ms": dm_poll_settings["active_interval_ms"],
                "combat_poll_idle_interval_ms": dm_poll_settings["idle_interval_ms"],
                "combat_poll_idle_threshold_ms": dm_poll_settings["idle_threshold_ms"],
            }
        )
        context["combat_subpages"] = build_combat_subpages(
            campaign_slug,
            current_subpage="dm",
            include_character_subpage=selected_character_combatant_id is not None,
            selected_combatant_id=resolved_selected_combatant_id,
            selected_character_combatant_id=selected_character_combatant_id,
            selected_character_slug=selected_character_slug,
        )
        context["show_clear_tracker_in_summary"] = False
        return context

    def build_campaign_dm_content_page_context(
        campaign_slug: str,
        *,
        dm_content_subpage: str = "statblocks",
        dm_statblock_form_overrides=None,
        dm_condition_form_overrides=None,
        player_wiki_edit_record=None,
        player_wiki_form_data=None,
        custom_systems_edit_entry=None,
        custom_systems_entry_form_data=None,
        systems_import_form_data=None,
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        dm_content_service = get_campaign_dm_content_service()
        can_manage_dm_content = can_manage_campaign_dm_content(campaign_slug)
        can_manage_content = can_manage_campaign_content(campaign_slug)
        can_manage_session = can_manage_campaign_session(campaign_slug)
        can_manage_systems = can_manage_campaign_systems(campaign_slug)
        normalized_subpage = normalize_dm_content_subpage(dm_content_subpage, allow_default=True)
        statblocks = dm_content_service.list_statblocks(campaign_slug)
        top_level_statblocks, statblock_subsection_groups = build_dm_statblock_subsection_groups(statblocks)
        custom_conditions = dm_content_service.list_condition_definitions(campaign_slug)
        systems_management_context: dict[str, object] = {}
        systems_management_count = 0
        if can_manage_systems:
            if normalized_subpage == "systems":
                systems_management_context = build_campaign_systems_control_context(
                    campaign_slug,
                    return_to="dm-content-systems",
                    active_nav="dm_content",
                    custom_systems_edit_entry=custom_systems_edit_entry,
                    custom_systems_entry_form_data=custom_systems_entry_form_data,
                    systems_import_form_data=systems_import_form_data,
                )
                systems_management_count = int(systems_management_context.get("systems_management_count") or 0)
            else:
                systems_management_count = len(get_systems_service().list_campaign_source_states(campaign_slug))
        player_wiki_records = []
        player_wiki_pages = []
        player_wiki_page_count = len(campaign.pages) if can_manage_content else 0
        player_wiki_query = request.args.get("q", "").strip()
        if can_manage_content and normalized_subpage == "player-wiki":
            player_wiki_records = list_campaign_page_files(
                campaign,
                page_store=get_campaign_page_store(),
            )
            player_wiki_page_count = len(player_wiki_records)
            player_wiki_removal_safety = build_dm_player_wiki_removal_safety_index(
                campaign_slug,
                campaign,
                player_wiki_records,
                session_articles=get_campaign_session_service().list_articles(campaign_slug),
                character_records=get_character_repository().list_characters(campaign_slug),
            )
            player_wiki_pages = [
                build_dm_player_wiki_page_summary(
                    campaign,
                    record,
                    removal_safety=player_wiki_removal_safety.get(record.page_ref),
                )
                for record in player_wiki_records
            ]
            if player_wiki_query:
                lowered_query = player_wiki_query.lower()
                player_wiki_pages = [
                    page
                    for page in player_wiki_pages
                    if lowered_query in str(page["search_text"])
                ]
        session_service = get_campaign_session_service()
        staged_article_count = (
            len(session_service.list_articles(campaign_slug, statuses=("staged",)))
            if can_manage_session
            else 0
        )
        staged_articles = []
        session_article_form_mode = normalize_session_article_form_mode(
            request.args.get("article_mode", "manual")
        )
        active_session = None
        chat_is_open = False
        if normalized_subpage == "staged-articles" and can_manage_session:
            session_context = build_campaign_session_page_context(campaign_slug, session_subpage="dm")
            staged_articles = list(session_context["staged_articles"] or [])
            session_article_form_mode = str(session_context["session_article_form_mode"] or "manual")
            active_session = session_context["active_session"]
            chat_is_open = bool(session_context["chat_is_open"])

        dm_content_subpages = []
        for subpage_key, label in DM_CONTENT_SUBPAGE_LABELS.items():
            if subpage_key == "player-wiki" and not can_manage_content:
                continue
            if subpage_key == "systems" and not can_manage_systems:
                continue
            if subpage_key == "staged-articles" and not can_manage_session:
                continue
            count = 0
            if subpage_key == "player-wiki":
                count = player_wiki_page_count
            elif subpage_key == "systems":
                count = systems_management_count
            elif subpage_key == "statblocks":
                count = len(statblocks)
            elif subpage_key == "staged-articles":
                count = staged_article_count
            else:
                count = len(custom_conditions)
            dm_content_subpages.append(
                {
                    "key": subpage_key,
                    "label": label,
                    "count": count,
                    "is_active": subpage_key == normalized_subpage,
                    "href": url_for(
                        "campaign_dm_content_subpage_view",
                        campaign_slug=campaign.slug,
                        dm_content_subpage=subpage_key,
                    ),
                }
            )

        return {
            "campaign": campaign,
            "dm_content_system_supported": supports_dnd5e_statblock_upload(campaign.system),
            "dm_statblocks": statblocks,
            "dm_statblock_top_level": top_level_statblocks,
            "dm_statblock_subsection_groups": statblock_subsection_groups,
            "dm_statblock_show_subsections": bool(statblock_subsection_groups),
            "dm_statblock_form_overrides": dm_statblock_form_overrides or {},
            "custom_condition_definitions": custom_conditions,
            "dm_condition_form_overrides": dm_condition_form_overrides or {},
            "can_manage_dm_content": can_manage_dm_content,
            "can_manage_content": can_manage_content,
            "can_manage_session": can_manage_session,
            "can_manage_systems": can_manage_systems,
            "dm_content_subpage": normalized_subpage,
            "dm_content_subpage_label": DM_CONTENT_SUBPAGE_LABELS[normalized_subpage],
            "dm_content_subpages": dm_content_subpages,
            "player_wiki_pages": player_wiki_pages,
            "player_wiki_page_count": player_wiki_page_count,
            "player_wiki_query": player_wiki_query,
            "player_wiki_section_choices": list_section_choices(),
            "player_wiki_form": build_dm_player_wiki_form(
                campaign,
                record=player_wiki_edit_record,
                form_data=player_wiki_form_data,
            ),
            "player_wiki_edit_record": player_wiki_edit_record,
            "staged_articles": staged_articles,
            "staged_article_count": staged_article_count,
            "session_article_form_mode": session_article_form_mode,
            "active_session": active_session,
            "chat_is_open": chat_is_open,
            "active_nav": "dm_content",
            **systems_management_context,
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
            base_visibility = current_visibility or get_campaign_default_scope_visibility(campaign_slug, scope)
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

    def build_campaign_systems_control_context(
        campaign_slug: str,
        *,
        return_to: str = "",
        active_nav: str = "systems",
        custom_systems_edit_entry=None,
        custom_systems_entry_form_data=None,
        systems_import_form_data=None,
    ) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        user = get_current_user()
        include_private = bool(user and user.is_admin)
        systems_service = get_systems_service()
        policy = systems_service.get_campaign_policy(campaign_slug)
        source_states = systems_service.list_campaign_source_states(campaign_slug)
        source_rows = []
        for state in source_states:
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

        entry_override_form_entry_key = request.args.get("entry_key", "").strip()
        library_slug = policy.library_slug if policy is not None else systems_service.get_campaign_library_slug(campaign_slug)
        entry_override_rows = []
        if library_slug:
            for override in systems_service.store.list_campaign_entry_overrides(campaign_slug, library_slug):
                entry = systems_service.store.get_entry(library_slug, override.entry_key)
                source_state = (
                    systems_service.get_campaign_source_state(campaign_slug, entry.source_id)
                    if entry is not None
                    else None
                )
                visibility_label = (
                    VISIBILITY_LABELS.get(override.visibility_override, override.visibility_override)
                    if override.visibility_override
                    else "Inherit source default"
                )
                if override.is_enabled_override is None:
                    enablement_label = "Inherit source enablement"
                elif override.is_enabled_override:
                    enablement_label = "Enabled"
                else:
                    enablement_label = "Disabled"
                entry_override_rows.append(
                    {
                        "entry_key": override.entry_key,
                        "entry_title": entry.title if entry is not None else "Unknown entry",
                        "entry_type_label": (
                            SYSTEMS_ENTRY_TYPE_LABELS.get(entry.entry_type, entry.entry_type.replace("_", " ").title())
                            if entry is not None
                            else ""
                        ),
                        "entry_href": (
                            url_for(
                                "campaign_systems_entry_detail",
                                campaign_slug=campaign.slug,
                                entry_slug=entry.slug,
                            )
                            if entry is not None and can_access_campaign_systems_entry(campaign_slug, entry.slug)
                            else ""
                        ),
                        "source_label": (
                            f"{source_state.source.title} ({source_state.source.source_id})"
                            if source_state is not None
                            else (entry.source_id if entry is not None else "")
                        ),
                        "visibility_label": visibility_label,
                        "enablement_label": enablement_label,
                    }
                )

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
            entry_count = len(entries)
            custom_entry_count += entry_count
            active_entry_count = 0
            entry_rows = []
            for entry in entries:
                override = systems_service.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
                is_archived = bool(override is not None and override.is_enabled_override is False)
                if not is_archived:
                    active_entry_count += 1
                entry_visibility = (
                    override.visibility_override
                    if override is not None and override.visibility_override
                    else systems_service.get_default_entry_visibility_for_campaign(campaign_slug, entry)
                )
                entry_rows.append(
                    {
                        "dom_id": custom_systems_entry_dom_id(entry),
                        "title": entry.title,
                        "entry_key": entry.entry_key,
                        "entry_slug": entry.slug,
                        "entry_type_label": SYSTEMS_ENTRY_TYPE_LABELS.get(
                            entry.entry_type,
                            entry.entry_type.replace("_", " ").title(),
                        ),
                        "source_id": entry.source_id,
                        "visibility_label": VISIBILITY_LABELS.get(entry_visibility, entry_visibility),
                        "status_label": "Archived" if is_archived else "Active",
                        "is_archived": is_archived,
                        "provenance": str((entry.metadata or {}).get("provenance") or entry.source_path or ""),
                        "search_metadata": str((entry.metadata or {}).get("search_metadata") or ""),
                        "rendered_html": entry.rendered_html,
                        "href": (
                            url_for(
                                "campaign_systems_entry_detail",
                                campaign_slug=campaign.slug,
                                entry_slug=entry.slug,
                            )
                            if can_access_campaign_systems_entry(campaign_slug, entry.slug)
                            else ""
                        ),
                        "edit_href": url_for(
                            "campaign_systems_control_panel_edit_custom_entry",
                            campaign_slug=campaign.slug,
                            entry_slug=entry.slug,
                            return_to=return_to or None,
                            _anchor="systems-custom-entry-editor",
                        ),
                        "archive_href": url_for(
                            "campaign_systems_control_panel_archive_custom_entry",
                            campaign_slug=campaign.slug,
                            entry_slug=entry.slug,
                        ),
                        "restore_href": url_for(
                            "campaign_systems_control_panel_restore_custom_entry",
                            campaign_slug=campaign.slug,
                            entry_slug=entry.slug,
                        ),
                    }
                )
            custom_entry_source_rows.append(
                {
                    "source_id": state.source.source_id,
                    "title": state.source.title,
                    "is_enabled": state.is_enabled,
                    "default_visibility_label": VISIBILITY_LABELS.get(
                        state.default_visibility,
                        state.default_visibility,
                    ),
                    "entry_count": entry_count,
                    "active_entry_count": active_entry_count,
                    "archived_entry_count": entry_count - active_entry_count,
                    "entries": entry_rows,
                }
            )

        custom_entry_form_visibility = systems_service.get_custom_campaign_entry_default_visibility(
            campaign_slug
        )
        if custom_systems_edit_entry is not None:
            edit_override = systems_service.store.get_campaign_entry_override(
                campaign_slug,
                custom_systems_edit_entry.entry_key,
            )
            custom_entry_form_visibility = (
                edit_override.visibility_override
                if edit_override is not None and edit_override.visibility_override
                else systems_service.get_default_entry_visibility_for_campaign(
                    campaign_slug,
                    custom_systems_edit_entry,
                )
            )

        import_run_rows = []
        if library_slug:
            for import_run in systems_service.store.list_import_runs(library_slug=library_slug, limit=10):
                summary = dict(import_run.summary or {})
                imported_by_type = summary.get("imported_by_type")
                type_summary = []
                if isinstance(imported_by_type, dict):
                    for entry_type, count in sorted(imported_by_type.items()):
                        type_summary.append(
                            f"{SYSTEMS_ENTRY_TYPE_LABELS.get(str(entry_type), str(entry_type).replace('_', ' ').title())}: {count}"
                        )
                source_files = summary.get("source_files")
                import_run_rows.append(
                    {
                        "id": import_run.id,
                        "source_id": import_run.source_id,
                        "status": import_run.status,
                        "import_version": import_run.import_version,
                        "imported_count": summary.get("imported_count"),
                        "type_summary": type_summary,
                        "source_files": source_files if isinstance(source_files, list) else [],
                        "source_file_count": len(source_files) if isinstance(source_files, list) else None,
                        "error": str(summary.get("error") or ""),
                        "started_at": import_run.started_at,
                        "completed_at": import_run.completed_at,
                    }
                )

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
            "campaign": campaign,
            "systems_library": library_slug if policy is not None else "",
            "systems_scope_visibility_label": VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "systems")],
            "source_rows": source_rows,
            "has_proprietary_sources": any(row["license_class"] == "proprietary_private" for row in source_rows),
            "proprietary_acknowledged": bool(policy and policy.proprietary_acknowledged_at is not None),
            "allow_dm_shared_core_entry_edits": bool(policy and policy.allow_dm_shared_core_entry_edits),
            "can_manage_shared_core_entry_edit_permission": bool(user and user.is_admin),
            "can_set_private_visibility": include_private,
            "systems_management_return_to": return_to,
            "entry_override_form_entry_key": entry_override_form_entry_key,
            "entry_override_rows": entry_override_rows,
            "entry_override_count": len(entry_override_rows),
            "custom_entry_source_rows": custom_entry_source_rows,
            "custom_entry_count": custom_entry_count,
            "custom_systems_edit_entry": custom_systems_edit_entry,
            "custom_systems_entry_form": build_dm_custom_systems_entry_form(
                entry=custom_systems_edit_entry,
                form_data=custom_systems_entry_form_data,
                visibility=custom_entry_form_visibility,
            ),
            "custom_systems_entry_type_choices": build_dm_custom_systems_entry_type_choices(
                library_slug=library_slug,
            ),
            "custom_systems_entry_visibility_choices": list_visibility_choices(include_private=include_private),
            "systems_import_form": build_systems_import_form(systems_import_form_data),
            "systems_import_source_choices": import_source_choices,
            "systems_import_entry_type_choices": build_systems_import_entry_type_choices(),
            "can_import_shared_systems": bool(user and user.is_admin),
            "import_run_rows": import_run_rows,
            "import_run_count": len(import_run_rows),
            "systems_management_count": len(source_rows),
            "active_nav": active_nav,
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
            accessible_source_entries = list_shared_accessible_campaign_source_entries(
                campaign_slug,
                state.source.source_id,
                systems_service=systems_service,
                can_access_campaign_systems_entry=can_access_campaign_systems_entry,
                limit=None,
            )
            source_has_rules_reference_entries = bool(
                filter_shared_accessible_systems_entries(
                    campaign_slug,
                    systems_service.list_rules_reference_entries_for_campaign(
                        campaign_slug,
                        include_source_ids=[state.source.source_id],
                        limit=None,
                    ),
                    can_access_campaign_systems_entry=can_access_campaign_systems_entry,
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
            for entry in filter_shared_accessible_systems_entries(
                campaign_slug,
                systems_service.search_entries_for_campaign(
                    campaign_slug,
                    query=search_query,
                    include_source_ids=include_source_ids,
                    limit=None,
                ),
                can_access_campaign_systems_entry=can_access_campaign_systems_entry,
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
            for entry in filter_shared_accessible_systems_entries(
                campaign_slug,
                systems_service.search_rules_reference_entries_for_campaign(
                    campaign_slug,
                    query=rules_reference_query,
                    include_source_ids=global_rules_reference_source_ids,
                    limit=None,
                ),
                can_access_campaign_systems_entry=can_access_campaign_systems_entry,
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
            accessible_entries = list_shared_accessible_campaign_source_entries(
                campaign_slug,
                source_id,
                systems_service=systems_service,
                can_access_campaign_systems_entry=can_access_campaign_systems_entry,
                entry_type=entry_type,
                limit=None,
            )
            if not accessible_entries:
                continue
            accessible_entries_by_type[entry_type] = accessible_entries
            all_entry_groups.append(
                {
                    "entry_type": entry_type,
                    "label": systems_entry_type_label(entry_type),
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
        rules_reference_entries = filter_shared_accessible_systems_entries(
            campaign_slug,
            raw_rules_reference_entries,
            can_access_campaign_systems_entry=can_access_campaign_systems_entry,
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
            for entry in filter_shared_accessible_systems_entries(
                campaign_slug,
                systems_service.search_rules_reference_entries_for_campaign(
                    campaign_slug,
                    query=rules_reference_query,
                    include_source_ids=[source_id],
                    limit=None,
                ),
                can_access_campaign_systems_entry=can_access_campaign_systems_entry,
                limit=100,
            ):
                rules_reference_results.append(build_rules_reference_search_result(entry))
        return {
            "campaign": campaign,
            "source_state": state,
            "source_browse_intro": systems_source_browse_intro(state.source.library_slug),
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
            list_shared_accessible_campaign_source_entries(
                campaign_slug,
                source_id,
                systems_service=systems_service,
                can_access_campaign_systems_entry=can_access_campaign_systems_entry,
                entry_type=normalized_entry_type,
                limit=None,
            )
        )
        if not entry_count:
            abort(404)
        normalized_query = query.strip()
        entries = list_shared_accessible_campaign_source_entries(
            campaign_slug,
            source_id,
            systems_service=systems_service,
            can_access_campaign_systems_entry=can_access_campaign_systems_entry,
            entry_type=normalized_entry_type,
            query=normalized_query,
            limit=None,
        )
        return {
            "campaign": campaign,
            "source_state": state,
            "entry_type": normalized_entry_type,
            "entry_type_label": systems_entry_type_label(normalized_entry_type),
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
        is_campaign_custom_entry = systems_service.is_campaign_custom_entry(campaign_slug, entry)

        def filter_base_rule_refs(value: object) -> list[dict[str, object]]:
            filtered_refs: list[dict[str, object]] = []
            for raw_item in list(value or []):
                item = dict(raw_item or {}) if isinstance(raw_item, dict) else {}
                target_entry = item.get("entry")
                if target_entry is None or not can_access_campaign_systems_entry(campaign_slug, target_entry.slug):
                    continue
                filtered_refs.append(item)
            return filtered_refs

        def filter_embedded_card(value: object) -> dict[str, object] | None:
            card = dict(value or {}) if isinstance(value, dict) else {}
            if not card:
                return None
            card["base_rule_refs"] = filter_base_rule_refs(card.get("base_rule_refs"))
            return card

        def filter_progression_groups(value: object) -> list[dict[str, object]]:
            filtered_groups: list[dict[str, object]] = []
            for raw_group in list(value or []):
                group = dict(raw_group or {}) if isinstance(raw_group, dict) else {}
                if not group:
                    continue
                filtered_rows: list[dict[str, object]] = []
                for raw_row in list(group.get("feature_rows") or []):
                    row = dict(raw_row or {}) if isinstance(raw_row, dict) else {}
                    if not row:
                        continue
                    row["embedded_card"] = filter_embedded_card(row.get("embedded_card"))
                    filtered_rows.append(row)
                group["feature_rows"] = filtered_rows
                filtered_groups.append(group)
            return filtered_groups

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
        class_feature_progression_groups = filter_progression_groups(class_feature_progression_groups)
        subclass_feature_progression_groups = filter_progression_groups(subclass_feature_progression_groups)
        feature_detail_card = (
            systems_service.build_feature_detail_card(campaign_slug, entry)
            if entry.entry_type in {"classfeature", "subclassfeature", "optionalfeature"}
            else None
        )
        feature_detail_card = filter_embedded_card(feature_detail_card)
        active_campaign_overlays = systems_service.build_active_campaign_overlays_for_entry(
            campaign_slug,
            entry,
        )
        related_rule_entries = [
            candidate
            for candidate in systems_service.build_related_rules_for_entry(campaign_slug, entry)
            if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
        ]
        source_chapter_context_entries = []
        for candidate in systems_service.build_source_chapter_context_entries_for_entry(
            campaign_slug,
            entry,
        ):
            if not isinstance(candidate, dict):
                continue
            context_entry = candidate.get("entry")
            if context_entry is None or not can_access_campaign_systems_entry(
                campaign_slug,
                context_entry.slug,
            ):
                continue
            source_chapter_context_entries.append(candidate)
        related_race_entries = []
        related_feat_entries = []
        related_item_entries = []
        related_monster_entries = []
        book_source_context_sections = []
        book_source_context_note = ""
        book_headers = []
        book_section_outline = []
        if entry.entry_type == "book":
            related_race_entries = [
                candidate
                for candidate in systems_service.build_related_races_for_entry(campaign_slug, entry)
                if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
            ]
            related_feat_entries = [
                candidate
                for candidate in systems_service.build_related_feats_for_entry(campaign_slug, entry)
                if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
            ]
            related_item_entries = [
                candidate
                for candidate in systems_service.build_related_items_for_entry(campaign_slug, entry)
                if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
            ]
            related_monster_entries = [
                candidate
                for candidate in systems_service.build_related_monsters_for_entry(campaign_slug, entry)
                if can_access_campaign_systems_entry(campaign_slug, candidate.slug)
            ]
            book_source_context_sections = systems_service.build_source_context_sections_for_entry(entry)
            if book_source_context_sections:
                book_source_context_note = (
                    "These VGM sections are preserved as readable source context for roleplaying, lair, tactics, "
                    "and variant-ability guidance. The app does not currently model them automatically."
                )
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
            "active_campaign_overlays": active_campaign_overlays,
            "related_rule_entries": related_rule_entries,
            "source_chapter_context_entries": source_chapter_context_entries,
            "related_race_entries": related_race_entries,
            "related_feat_entries": related_feat_entries,
            "related_item_entries": related_item_entries,
            "related_monster_entries": related_monster_entries,
            "book_source_context_sections": book_source_context_sections,
            "book_source_context_note": book_source_context_note,
            "book_headers": book_headers,
            "book_section_outline": book_section_outline,
            "book_default_visibility_label": book_default_visibility_label,
            "book_visibility_policy_note": book_visibility_policy_note,
            "source_state": source_state,
            "can_manage_systems": can_manage_campaign_systems(campaign_slug),
            "is_campaign_custom_entry": is_campaign_custom_entry,
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
                    "controls_html": render_template("_session_status_controls_card.html", **context),
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
        requested_detail_state_token: str = "",
        include_flash: bool = False,
        mutation_succeeded: bool | None = None,
        anchor: str | None = None,
        selected_combatant_id: int | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
    ) -> dict[str, object]:
        thin_context = build_campaign_combat_page_context(
            campaign_slug,
            combat_subpage="combat",
            selected_combatant_id=selected_combatant_id,
            sync_player_character_snapshots=sync_player_character_snapshots,
            include_player_workspace_detail=False,
        )
        should_reuse_selected_detail = should_skip_selected_combatant_detail_render(
            requested_detail_state_token=requested_detail_state_token,
            selected_detail_state_token=str(thin_context.get("combat_character_state_token") or ""),
        )
        include_player_workspace_sections = not (
            bool(thin_context.get("show_player_combat_workspace"))
            and should_reuse_selected_detail
        )
        if include_player_workspace_sections:
            context = build_campaign_combat_page_context(
                campaign_slug,
                combat_subpage="combat",
                selected_combatant_id=selected_combatant_id,
                sync_player_character_snapshots=False,
            )
        else:
            context = thin_context
        if live_revision is None:
            live_revision = int(context["combat_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["combat_live_view_token"] or "")
        summary_template = "_combat_summary_card.html"
        tracker_template = (
            "_combat_player_workspace_sections.html"
            if context.get("show_player_combat_workspace")
            else "_combat_tracker_section.html"
        )
        sidebar_template = (
            "_combat_player_workspace_sidebar.html"
            if context.get("show_player_combat_workspace")
            else "_combat_context_panel.html"
        )
        payload = {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "combat_state_token": context["combat_live_state_token"],
            "combatant_detail_state_token": str(context.get("combat_character_state_token") or ""),
            "summary_html": (
                render_template(
                    summary_template,
                    combat_summary_compact=bool(context.get("show_player_combat_workspace")),
                    **context,
                )
                + (
                    render_template(
                        "_combat_combatant_navigation.html",
                        combatant_navigation_mode="carousel",
                        **context,
                    )
                    + render_template("_combat_character_snapshot.html", **context)
                    if context.get("show_player_combat_workspace")
                    else ""
                )
            ),
            "tracker_html": (
                render_template(tracker_template, **context)
                if include_player_workspace_sections
                else None
            ),
            "context_html": (
                render_template(sidebar_template, **context)
                if include_player_workspace_sections
                else None
            ),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        if "tracker_html" not in payload or payload["tracker_html"] is None:
            payload.pop("tracker_html", None)
        if "context_html" not in payload or payload["context_html"] is None:
            payload.pop("context_html", None)
        payload.update(
            build_combat_surface_urls(
                campaign_slug,
                combat_subpage="combat",
                selected_combatant_id=context["selected_combatant_id"],
            )
        )
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
        combat_dm_view: str | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
        include_selected_detail: bool = True,
        context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        normalized_combat_dm_view = normalize_combat_dm_view(combat_dm_view or "")
        if normalized_combat_dm_view == "controls":
            context = build_campaign_combat_page_context(
                campaign_slug,
                include_control_choices=True,
                combat_subpage="dm",
                selected_combatant_id=selected_combatant_id,
                combat_dm_view=normalized_combat_dm_view,
                sync_player_character_snapshots=sync_player_character_snapshots,
            )
        else:
            context = context or build_campaign_combat_dm_status_context(
                campaign_slug,
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
            "combatant_detail_state_token": str(context.get("combat_status_state_token") or ""),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        if normalized_combat_dm_view == "status":
            summary_context = dict(context)
            summary_context["combat_summary_compact"] = True
            summary_context["combat_summary_show_focus_picker"] = False
            payload.update(
                {
                    "summary_html": render_template(
                        "_combat_summary_card.html",
                        **summary_context,
                    ),
                    "tracker_html": render_template(
                        "_combat_combatant_navigation.html",
                        combatant_navigation_mode="carousel",
                        **context,
                    ),
                    "tracker_authority_html": render_template("_combat_dm_selected_authority.html", **context),
                }
            )
            if include_selected_detail:
                payload["tracker_detail_html"] = _build_cached_combat_status_detail_html(
                    campaign_slug=campaign_slug,
                    detail_view="combat-dm-status",
                    selected_combatant_state_token=str(context.get("combat_status_state_token") or ""),
                    context=context,
                )
        else:
            payload["controls_html"] = render_template("_combat_dm_controls.html", **context)
        payload.update(
            build_combat_surface_urls(
                campaign_slug,
                combat_subpage="dm",
                selected_combatant_id=context["selected_combatant_id"],
                combat_dm_view=normalized_combat_dm_view,
            )
        )
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
        selected_combatant_id: int | None = None,
        live_revision: int | None = None,
        live_view_token: str | None = None,
        sync_player_character_snapshots: bool = True,
        include_selected_detail: bool = True,
        context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        context = (
            context
            if context is not None
            else build_campaign_combat_status_context(
                campaign_slug,
                selected_combatant_id=selected_combatant_id,
                sync_player_character_snapshots=sync_player_character_snapshots,
                strict_selected_combatant=False,
            )
        )
        if live_revision is None:
            live_revision = int(context["combat_live_revision"] or 0)
        if live_view_token is None:
            live_view_token = str(context["combat_live_view_token"] or "")
        selected_combatant_state_token = str(context["combat_status_state_token"] or "")
        payload = {
            "changed": True,
            "live_revision": live_revision,
            "live_view_token": live_view_token,
            "combat_state_token": context["combat_live_state_token"],
            "combatant_detail_state_token": selected_combatant_state_token,
            "board_html": render_template("_combat_status_board.html", **context),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        if include_selected_detail:
            payload["detail_html"] = _build_cached_combat_status_detail_html(
                campaign_slug=campaign_slug,
                detail_view="combat-status",
                selected_combatant_state_token=selected_combatant_state_token,
                context=context,
            )
        payload.update(
            build_combat_surface_urls(
                campaign_slug,
                combat_subpage="status",
                selected_combatant_id=context["selected_combatant_id"],
            )
        )
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
        ignore_requested_combatant_for_dm: bool = False,
        fallback_combatant_id: int | None = None,
    ):
        combat_return_view = normalize_combat_return_view(request.values.get("combat_view", ""))
        combat_dm_view = normalize_combat_dm_view(request.values.get("view", ""))
        selected_combatant_id = (
            None
            if ignore_requested_combatant_for_dm and combat_return_view == "dm"
            else get_requested_combatant_id_from_values() or fallback_combatant_id
        )
        if is_async_request():
            if combat_return_view == "dm":
                return jsonify(
                    build_campaign_combat_dm_live_state(
                        campaign_slug,
                        include_flash=True,
                        mutation_succeeded=mutation_succeeded,
                        anchor=anchor,
                        selected_combatant_id=selected_combatant_id,
                        combat_dm_view=combat_dm_view,
                    )
                )
            if combat_return_view == "status":
                return jsonify(
                    build_campaign_combat_status_live_state(
                        campaign_slug,
                        include_flash=True,
                        mutation_succeeded=mutation_succeeded,
                        selected_combatant_id=selected_combatant_id,
                    )
                )
            if combat_return_view == "character":
                payload = build_campaign_combat_character_live_state(campaign_slug)
                payload["flash_html"] = render_flash_stack_html()
                payload["ok"] = mutation_succeeded
                if anchor:
                    payload["anchor"] = anchor
                return jsonify(payload)
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
                combat_dm_view=combat_dm_view,
            )
        if combat_return_view == "status":
            return redirect_to_campaign_combat_status(
                campaign_slug,
                anchor=anchor,
                combatant_id=selected_combatant_id,
            )
        if combat_return_view == "character":
            return redirect_to_campaign_combat_character(
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
        def _build_loading_media_urls() -> list[str]:
            view_args = request.view_args or {}
            campaign_slug = str(view_args.get("campaign_slug", "")).strip()
            return _build_campaign_loading_media_urls(campaign_slug)

        loading_media_urls = _build_loading_media_urls()
        loading_image_url = loading_media_urls[0] if loading_media_urls else None
        return {
            "slugify": slugify,
            "app_metadata": build_app_metadata(app.config),
            "stylesheet_url": _build_stylesheet_url,
            "static_asset_url": _build_static_asset_url,
            "app_loading_media_urls": loading_media_urls,
            "app_loading_image_url": loading_image_url,
        }

    @app.errorhandler(404)
    def not_found(_: Exception):
        return render_template("not_found.html"), 404

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(error: RequestEntityTooLarge):
        if request.path.startswith("/api/v1/"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": {
                            "code": "request_too_large",
                            "message": "The request is too large.",
                        },
                    }
                ),
                413,
            )
        return error.get_response()

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

    @app.get("/livez")
    def liveness():
        return jsonify(liveness_payload())

    @app.get("/readyz")
    def readiness():
        payload, status_code = readiness_payload(
            database_path=app.config["DB_PATH"],
            campaigns_dir=app.config["CAMPAIGNS_DIR"],
        )
        return jsonify(payload), status_code

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
        latest_session_summary = None
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
            if not query:
                latest_session_summary = repository.get_latest_session_summary_page(campaign_slug)

        return render_template(
            "campaign.html",
            campaign=campaign,
            grouped_pages=grouped_pages,
            query=query,
            result_count=result_count,
            latest_session_summary=latest_session_summary,
            can_view_wiki=can_view_wiki,
            wiki_visibility_label=VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "wiki")],
            active_nav="wiki",
        )

    @app.get("/campaigns/<campaign_slug>/global-search")
    @campaign_scope_access_required("campaign")
    def campaign_global_search(campaign_slug: str):
        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify(
                {
                    "results": [],
                    "message": "Type at least 2 letters to search wiki pages and Systems entries.",
                }
            )

        results = build_campaign_global_search_results(campaign_slug, query, limit=30)
        message = (
            "Showing the first 30 matching references."
            if len(results) == 30
            else (
                f"Found {len(results)} matching reference{'s' if len(results) != 1 else ''}."
                if results
                else "No visible wiki pages or Systems entries matched that search."
            )
        )
        return jsonify({"results": results, "message": message})

    @app.get("/campaigns/<campaign_slug>/global-search/preview")
    @campaign_scope_access_required("campaign")
    def campaign_global_search_preview(campaign_slug: str):
        result_id = request.args.get("result_id", "").strip()
        if not result_id:
            return jsonify({"preview_html": ""})

        preview_context = build_campaign_global_search_preview_context(campaign_slug, result_id)
        if preview_context is None:
            return (
                jsonify(
                    {
                        "preview_html": render_template(
                            "_campaign_global_search_preview.html",
                            result_unavailable_message="That reference is not currently visible.",
                        )
                    }
                ),
                404,
            )

        return jsonify(
            {
                "preview_html": render_template(
                    "_campaign_global_search_preview.html",
                    **preview_context,
                )
            }
        )

    @app.get("/campaigns/<campaign_slug>/help")
    @campaign_scope_access_required("campaign")
    def campaign_help_view(campaign_slug: str):
        context = build_campaign_help_context(campaign_slug)
        return render_template("campaign_help.html", **context)

    register_session_routes(
        app,
        build_campaign_session_shell_context=build_campaign_session_shell_context,
        build_session_live_metadata=build_session_live_metadata,
        build_campaign_session_live_state=build_campaign_session_live_state,
        build_live_json_response=build_live_json_response,
        build_session_article_convert_context=build_session_article_convert_context,
        normalize_publish_options=lambda **kwargs: normalize_publish_options(**kwargs),
        publish_session_article=lambda *args, **kwargs: publish_session_article(*args, **kwargs),
        refresh_repository_store=lambda: repository_store.refresh(),
        normalize_session_article_form_mode=normalize_session_article_form_mode,
        create_session_article_from_request=create_session_article_from_request,
        update_session_article_from_request=update_session_article_from_request,
        load_campaign_context=load_campaign_context,
        get_campaign_session_service=get_campaign_session_service,
        get_campaign_page_store=get_campaign_page_store,
        get_systems_service=get_systems_service,
        can_player_access_campaign_scope=can_player_access_campaign_scope,
        build_player_session_wiki_search_results=build_player_session_wiki_search_results,
        build_player_session_wiki_lookup_preview_context=build_player_session_wiki_lookup_preview_context,
        respond_to_campaign_session_mutation=respond_to_campaign_session_mutation,
        redirect_to_campaign_session_dm=redirect_to_campaign_session_dm,
    )
    register_publishing_routes(
        app,
        dm_content_context_builder=build_campaign_dm_content_page_context,
    )
    register_dm_content_routes(
        app,
        load_campaign=load_campaign_context,
        get_service=get_campaign_dm_content_service,
        build_page_context=build_campaign_dm_content_page_context,
        redirect_to_dm_content=redirect_to_campaign_dm_content,
    )
    register_systems_routes(
        app,
        build_index_context=build_campaign_systems_index_context,
        build_source_context=build_campaign_systems_source_context,
        build_source_category_context=build_campaign_systems_source_category_context,
        build_entry_context=build_campaign_systems_entry_context,
        load_campaign=load_campaign_context,
        get_service=get_systems_service,
        build_control_context=build_campaign_systems_control_context,
        build_dm_content_context=build_campaign_dm_content_page_context,
        redirect_to_dm_content=redirect_to_campaign_dm_content,
        custom_entry_dom_id=custom_systems_entry_dom_id,
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
            default_visibility = get_campaign_default_scope_visibility(campaign_slug, scope)
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

    @app.get("/campaigns/<campaign_slug>/systems/control-panel")
    @login_required
    def campaign_systems_control_panel_view(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)
        context = build_campaign_systems_control_context(campaign_slug)
        return render_template("campaign_systems_control_panel.html", **context)

    @app.get("/campaigns/<campaign_slug>/dm-content")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_view(campaign_slug: str):
        context = build_campaign_dm_content_page_context(campaign_slug, dm_content_subpage="statblocks")
        return render_template("dm_content.html", **context)

    @app.get("/campaigns/<campaign_slug>/dm-content/<dm_content_subpage>")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_subpage_view(campaign_slug: str, dm_content_subpage: str):
        normalized_subpage = normalize_dm_content_subpage(dm_content_subpage)
        if not normalized_subpage:
            abort(404)
        if normalized_subpage == "systems" and not can_manage_campaign_systems(campaign_slug):
            abort(403)
        context = build_campaign_dm_content_page_context(
            campaign_slug,
            dm_content_subpage=normalized_subpage,
        )
        return render_template("dm_content.html", **context)

    @app.post("/campaigns/<campaign_slug>/dm-content/staged-articles")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_create_staged_article(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        article_mode = normalize_session_article_form_mode(request.form.get("article_mode", "manual"))
        source_kind = ""
        try:
            _, article_mode, source_kind = create_session_article_from_request(
                campaign_slug,
                created_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            if article_mode == "wiki":
                if source_kind == SESSION_ARTICLE_SOURCE_KIND_SYSTEMS:
                    flash("Systems entry added to staged articles.", "success")
                else:
                    flash("Published wiki page added to staged articles.", "success")
            else:
                flash("Staged article added to the session reveal queue.", "success")

        return redirect_to_campaign_dm_content(
            campaign_slug,
            article_mode=article_mode,
            subpage="staged-articles",
            anchor="dm-content-staged-article-store",
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/staged-articles/<int:article_id>")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_update_staged_article(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            update_session_article_from_request(
                campaign_slug,
                article_id,
                updated_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Staged article updated.", "success")

        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="staged-articles",
            anchor="dm-content-staged-articles-queue",
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/staged-articles/<int:article_id>/delete")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_delete_staged_article(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        session_service = get_campaign_session_service()
        article = session_service.get_article(campaign_slug, article_id)
        if article is None:
            flash("That session article could not be found.", "error")
        elif article.is_revealed:
            flash("Open Session DM to manage revealed articles.", "error")
        else:
            try:
                session_service.delete_article(
                    campaign_slug,
                    article_id,
                    updated_by_user_id=user.id,
                )
            except CampaignSessionValidationError as exc:
                flash(str(exc), "error")
            else:
                flash("Staged article deleted from the session reveal queue.", "success")

        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="staged-articles",
            anchor="dm-content-staged-articles-queue",
        )

    register_combat_routes(
        app,
        build_campaign_combat_page_context=build_campaign_combat_page_context,
        redirect_to_campaign_combat_dm=redirect_to_campaign_combat_dm,
        parse_requested_combatant_id=parse_requested_combatant_id,
        build_combat_live_metadata=build_combat_live_metadata,
        build_campaign_combat_live_state=build_campaign_combat_live_state,
        build_live_json_response=build_live_json_response,
        normalize_combat_dm_view=normalize_combat_dm_view,
        build_campaign_combat_dm_status_context=build_campaign_combat_dm_status_context,
        build_campaign_combat_dm_live_state=build_campaign_combat_dm_live_state,
        build_campaign_combat_status_context=build_campaign_combat_status_context,
        build_campaign_combat_status_live_state=build_campaign_combat_status_live_state,
        parse_live_detail_state_token_header=parse_live_detail_state_token_header,
        require_supported_combat_system=require_supported_combat_system,
        get_campaign_combat_service=get_campaign_combat_service,
        respond_to_campaign_combat_mutation=respond_to_campaign_combat_mutation,
        parse_expected_combatant_revision=parse_expected_combatant_revision,
        normalize_combat_return_view=normalize_combat_return_view,
        get_requested_combatant_id_from_values=get_requested_combatant_id_from_values,
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
        require_explicit_combat_character_target_access(campaign_slug)
        state_check_started_at = time.perf_counter()
        live_metadata = build_combat_live_metadata(campaign_slug, "character")
        snapshot_sync_metrics = live_metadata.get("snapshot_sync_metrics")
        state_check_ms = (time.perf_counter() - state_check_started_at) * 1000
        if should_short_circuit_shared_live_response(
            request.headers,
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
                snapshot_sync_metrics=snapshot_sync_metrics,
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
            snapshot_sync_metrics=snapshot_sync_metrics,
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
        campaign = load_campaign_context(campaign_slug)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            flash(DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE, "error")
            return redirect(url_for("campaign_view", campaign_slug=campaign_slug))

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

    @app.post("/campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/item-actions/<action_id>/use")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_item_action_use(
        campaign_slug: str,
        combatant_id: int,
        action_id: str,
    ):
        campaign = load_campaign_context(campaign_slug)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            flash(DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE, "error")
            return redirect(url_for("campaign_view", campaign_slug=campaign_slug))

        def _action(record, expected_revision, user_id):
            slot_lane_id, slot_level = parse_item_action_slot_selection(
                request.form.get("slot_selection")
            )
            if not slot_level:
                slot_level = int(request.form.get("slot_level") or 0)
                slot_lane_id = request.form.get("slot_lane_id", "")
            return get_character_state_service().use_spell_slot_item_action(
                record,
                resolve_projected_item_use_action(campaign_slug, campaign, record, action_id),
                choice_id=request.form.get("choice_id", ""),
                slot_level=slot_level,
                slot_lane_id=slot_lane_id,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            )

        return run_combat_character_mutation(
            campaign_slug,
            combatant_id,
            anchor="combat-character-equipment",
            success_message="Item action used.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/equipment/<item_id>/state")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_equipment_state(
        campaign_slug: str,
        combatant_id: int,
        item_id: str,
    ):
        item_catalog = build_character_item_catalog(campaign_slug)

        return run_combat_character_definition_mutation(
            campaign_slug,
            combatant_id,
            anchor="combat-character-equipment",
            success_message="Equipment state updated.",
            action=lambda record: build_shared_equipment_state_update_result(
                campaign_slug,
                record,
                item_id,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                values=build_equipment_state_form_values(),
            ),
        )

    @app.post("/campaigns/<campaign_slug>/combat/character/combatants/<int:combatant_id>/feature-states/<feature_key>")
    @campaign_scope_access_required("combat")
    def campaign_combat_character_feature_state(
        campaign_slug: str,
        combatant_id: int,
        feature_key: str,
    ):
        return run_combat_character_mutation(
            campaign_slug,
            combatant_id,
            anchor="combat-character-equipment",
            success_message="Feature state updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_feature_state(
                record,
                feature_key,
                expected_revision=expected_revision,
                enabled=request.form.get("enabled") == "1",
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

    register_combat_basic_seeding_routes(app)

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

        resource_counter_seeds, resource_note_seeds = build_npc_resource_seeds_from_markdown(
            statblock.body_markdown,
            source_label="DM Content",
        )
        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_npc_combatant(
                campaign_slug,
                display_name=request.form.get("display_name", "").strip() or statblock.title,
                turn_value=request.form.get("turn_value", "").strip() or statblock.initiative_bonus,
                initiative_bonus=statblock.initiative_bonus,
                dexterity_modifier=get_campaign_dm_content_service().get_statblock_dexterity_modifier(statblock),
                initiative_priority=request.form.get("initiative_priority"),
                current_hp=statblock.max_hp,
                max_hp=statblock.max_hp,
                temp_hp=0,
                movement_total=statblock.movement_total,
                source_kind=COMBAT_SOURCE_KIND_DM_STATBLOCK,
                source_ref=str(statblock.id),
                resource_counter_seeds=resource_counter_seeds,
                resource_note_seeds=resource_note_seeds,
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
        resource_counter_seeds, resource_note_seeds = build_npc_resource_seeds_from_systems_entry(
            monster_entry,
            source_label=f"Systems {monster_entry.source_id}",
        )

        mutation_succeeded = False
        try:
            get_campaign_combat_service().add_npc_combatant(
                campaign_slug,
                display_name=request.form.get("display_name", "").strip() or monster_entry.title,
                turn_value=request.form.get("turn_value", "").strip() or monster_seed.initiative_bonus,
                initiative_bonus=monster_seed.initiative_bonus,
                dexterity_modifier=monster_seed.dexterity_modifier,
                initiative_priority=request.form.get("initiative_priority"),
                current_hp=monster_seed.max_hp,
                max_hp=monster_seed.max_hp,
                temp_hp=0,
                movement_total=monster_seed.movement_total,
                source_kind=COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
                source_ref=monster_entry.entry_key,
                resource_counter_seeds=resource_counter_seeds,
                resource_note_seeds=resource_note_seeds,
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

    register_combat_advance_turn_route(app)

    register_combat_clear_route(app)

    register_combat_set_current_turn_route(app)

    register_combat_update_turn_value_route(app)

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
                    hit_dice_current=parse_hit_dice_current_values(),
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
            expected_combatant_revision = parse_expected_combatant_revision()
            combat_service.update_npc_vitals(
                campaign_slug,
                combatant_id,
                expected_revision=expected_combatant_revision,
                current_hp=request.form.get("current_hp"),
                max_hp=request.form.get("max_hp"),
                temp_hp=request.form.get("temp_hp"),
                movement_total=request.form.get("movement_total"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            flash("This combatant changed in another combat view. Refresh and try again.", "error")
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
            expected_combatant_revision = parse_expected_combatant_revision()
            combat_service.update_resources(
                campaign_slug,
                combatant_id,
                expected_revision=expected_combatant_revision,
                has_action=request.form.get("has_action") == "1",
                has_bonus_action=request.form.get("has_bonus_action") == "1",
                has_reaction=request.form.get("has_reaction") == "1",
                movement_remaining=request.form.get("movement_remaining"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            flash("This combatant changed in another combat view. Refresh and try again.", "error")
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

    register_combat_update_player_detail_visibility_route(app)

    register_combat_condition_routes(app)

    register_combat_delete_combatant_route(app)

    register_character_routes(
        app,
        build_campaign_session_character_page_context=(
            build_campaign_session_character_page_context
        ),
        build_campaign_session_shell_context=build_campaign_session_shell_context,
    )

    register_character_roster_route(
        app,
        get_repository=get_repository,
        campaign_supports_native_character_tools=campaign_supports_native_character_tools,
        campaign_supports_native_character_create=campaign_supports_native_character_create,
        native_character_create_lane=lambda value: native_character_create_lane(value),
        get_character_repository=get_character_repository,
        present_character_roster=lambda records: present_character_roster(records),
        can_manage_campaign_session=lambda campaign_slug: can_manage_campaign_session(
            campaign_slug
        ),
    )

    @app.route("/campaigns/<campaign_slug>/characters/new", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_create_view(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        create_lane = native_character_create_lane(getattr(campaign, "system", ""))
        if not campaign_supports_native_character_create(campaign) or not create_lane:
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                message=native_character_create_unsupported_message(campaign.system),
            )
        if create_lane == CHARACTER_ROUTE_LANE_XIANXIA:
            form_source = request.form if request.method == "POST" else request.args
            form_values = dict(form_source)
            if hasattr(form_source, "getlist"):
                grant_values = form_source.getlist(XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT)
                if grant_values:
                    form_values[XIANXIA_GM_GRANTED_GENERIC_TECHNIQUE_INPUT] = grant_values
            create_context = build_xianxia_character_create_context(
                form_values,
                systems_service=get_systems_service(),
                campaign_slug=campaign_slug,
            )
            if request.method != "POST":
                return render_xianxia_character_create_page(campaign_slug, create_context)

            try:
                definition, import_metadata = build_xianxia_character_definition(
                    campaign_slug,
                    create_context,
                    form_values,
                )
                initial_state = build_xianxia_character_initial_state(definition, form_values)
            except CharacterBuildError as exc:
                flash(str(exc), "error")
                return render_xianxia_character_create_page(campaign_slug, create_context, status_code=400)

            config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
            character_dir = config.characters_dir / definition.character_slug
            definition_path = character_dir / "definition.yaml"
            import_path = character_dir / "import.yaml"
            if definition_path.exists() or import_path.exists():
                flash(
                    f"A character with slug '{definition.character_slug}' already exists in this campaign.",
                    "error",
                )
                return render_xianxia_character_create_page(campaign_slug, create_context, status_code=409)

            write_yaml(definition_path, definition.to_dict())
            write_yaml(import_path, import_metadata.to_dict())
            character_state_store.initialize_state_if_missing(definition, initial_state)
            flash(f"{definition.name} created.", "success")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=definition.character_slug,
                )
            )
        if create_lane != CHARACTER_ROUTE_LANE_DND5E:
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                message=native_character_create_unsupported_message(campaign.system),
            )
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
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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

    @app.route("/campaigns/<campaign_slug>/characters/import/xianxia-manual", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_import_xianxia_manual_view(campaign_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        if native_character_create_lane(getattr(campaign, "system", "")) != CHARACTER_ROUTE_LANE_XIANXIA:
            flash("Manual Xianxia character import is only available for Xianxia campaigns.", "error")
            return redirect(url_for("character_roster_view", campaign_slug=campaign_slug))

        form_values = dict(request.form if request.method == "POST" else request.args)
        import_context = build_xianxia_manual_import_context(
            systems_service=get_systems_service(),
            campaign_slug=campaign_slug,
            values=form_values,
        )
        if request.method != "POST":
            return render_xianxia_manual_import_page(campaign_slug, import_context)

        payload = build_xianxia_manual_import_payload(form_values)
        try:
            definition, import_metadata, initial_state = build_xianxia_manual_import_character(
                payload,
                campaign_slug=campaign_slug,
                martial_art_options=list(import_context.get("martial_art_options") or []),
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return render_xianxia_manual_import_page(campaign_slug, import_context, status_code=400)

        preview = build_xianxia_manual_import_preview(definition, initial_state)
        import_context = build_xianxia_manual_import_context(
            systems_service=get_systems_service(),
            campaign_slug=campaign_slug,
            values=form_values,
            preview=preview,
        )
        if not request.form.get("confirm_import"):
            flash("Review the imported sheet summary, then confirm to create the character.", "info")
            return render_xianxia_manual_import_page(campaign_slug, import_context)

        config = load_campaign_character_config(app.config["CAMPAIGNS_DIR"], campaign_slug)
        character_dir = config.characters_dir / definition.character_slug
        definition_path = character_dir / "definition.yaml"
        import_path = character_dir / "import.yaml"
        if definition_path.exists() or import_path.exists():
            flash(
                f"A character with slug '{definition.character_slug}' already exists in this campaign.",
                "error",
            )
            return render_xianxia_manual_import_page(campaign_slug, import_context, status_code=409)

        write_yaml(definition_path, definition.to_dict())
        write_yaml(import_path, import_metadata.to_dict())
        character_state_store.initialize_state_if_missing(definition, initial_state)
        flash(f"{definition.name} imported.", "success")
        return redirect(
            url_for(
                "character_read_view",
                campaign_slug=campaign_slug,
                character_slug=definition.character_slug,
            )
        )

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/level-up", methods=["GET", "POST"])
    @login_required
    def character_level_up_view(campaign_slug: str, character_slug: str):
        if get_repository().get_campaign(campaign_slug) is None:
            abort(404)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_native_character_advancement(campaign):
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
                message=character_advancement_unsupported_message(campaign.system),
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
            if not can_manage_campaign_session(campaign_slug):
                return redirect(character_sheet_return_href(campaign_slug, character_slug))
            return redirect(
                url_for(
                    "character_progression_repair_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )
        if readiness.get("status") != "ready":
            flash(str(readiness.get("message") or "This character is not eligible for the current native level-up flow."), "error")
            return redirect(character_sheet_return_href(campaign_slug, character_slug))

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
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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
        return redirect(character_sheet_return_href(campaign_slug, character_slug))

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/cultivation", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_xianxia_cultivation_view(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if (
            character_advancement_lane(getattr(campaign, "system", ""))
            != CHARACTER_ADVANCEMENT_LANE_XIANXIA_CULTIVATION
            or not is_xianxia_system(getattr(record.definition, "system", ""))
        ):
            flash("Cultivation is only available for Xianxia character sheets.", "error")
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
            )

        if request.method == "POST":
            user = get_current_user()
            if user is None:
                abort(403)

            redirect_anchor = "xianxia-cultivation-insight"
            try:
                expected_revision = parse_expected_revision()
                cultivation_action = str(request.form.get("cultivation_action") or "save_insight").strip()
                if cultivation_action == "save_insight":
                    insight_available = normalize_dm_player_wiki_int(
                        request.form.get("insight_available", ""),
                        field_label="Insight available",
                    )
                    insight_spent = normalize_dm_player_wiki_int(
                        request.form.get("insight_spent", ""),
                        field_label="Insight spent",
                    )
                    definition = xianxia_cultivation.update_xianxia_insight_definition(
                        record.definition,
                        available=insight_available,
                        spent=insight_spent,
                    )
                    success_message = "Insight counters saved."
                elif cultivation_action == "record_gathering_insight":
                    redirect_anchor = "xianxia-cultivation-gathering-insight"
                    insight_gain = normalize_dm_player_wiki_int(
                        request.form.get("insight_gain_amount", ""),
                        field_label="Gathered Insight",
                    )
                    definition = xianxia_cultivation.update_xianxia_gathering_insight_definition(
                        record.definition,
                        amount=insight_gain,
                        downtime=request.form.get("gathering_insight_downtime", ""),
                        notes=request.form.get("gathering_insight_notes", ""),
                    )
                    success_message = "Gathering Insight recorded."
                elif cultivation_action == "spend_cultivation_energy":
                    redirect_anchor = "xianxia-cultivation-energy"
                    energy_result = spend_xianxia_cultivation_energy_definition(
                        record.definition,
                        energy_key=request.form.get("energy_key", ""),
                        notes=request.form.get("cultivation_energy_notes", ""),
                    )
                    definition = energy_result.definition
                    success_message = (
                        f"Spent {energy_result.insight_cost} Insight on Cultivation "
                        f"to increase {energy_result.energy_name}."
                    )
                elif cultivation_action == "spend_meditation_yin_yang":
                    redirect_anchor = "xianxia-cultivation-meditation"
                    meditation_result = spend_xianxia_meditation_definition(
                        record.definition,
                        yin_yang_key=request.form.get("yin_yang_key", ""),
                        notes=request.form.get("meditation_notes", ""),
                    )
                    definition = meditation_result.definition
                    success_message = (
                        f"Spent {meditation_result.insight_cost} Insight on Meditation "
                        f"to increase {meditation_result.yin_yang_name}."
                    )
                elif cultivation_action == "spend_conditioning":
                    redirect_anchor = "xianxia-cultivation-conditioning"
                    conditioning_result = spend_xianxia_conditioning_definition(
                        record.definition,
                        conditioning_target=request.form.get("conditioning_target", ""),
                        effort_key=request.form.get("effort_key", ""),
                        notes=request.form.get("conditioning_notes", ""),
                    )
                    definition = conditioning_result.definition
                    success_message = (
                        f"Spent {conditioning_result.insight_cost} Insight on Conditioning "
                        f"to increase {conditioning_result.target_name}."
                    )
                elif cultivation_action == "spend_training":
                    redirect_anchor = "xianxia-cultivation-training"
                    training_result = spend_xianxia_training_definition(
                        record.definition,
                        training_target=request.form.get("training_target", ""),
                        attribute_key=request.form.get("attribute_key", ""),
                        notes=request.form.get("training_notes", ""),
                    )
                    definition = training_result.definition
                    success_message = (
                        f"Spent {training_result.insight_cost} Insight on Training "
                        f"to increase {training_result.target_name}."
                    )
                elif cultivation_action == "advance_martial_art_rank":
                    redirect_anchor = "xianxia-cultivation-martial-arts"
                    raw_martial_art_index = request.form.get("martial_art_index", "")
                    if not str(raw_martial_art_index or "").strip():
                        raise ValueError("Martial Art selection is required.")
                    martial_art_index = normalize_dm_player_wiki_int(
                        raw_martial_art_index,
                        field_label="Martial Art selection",
                    )
                    rank_result = advance_xianxia_martial_art_rank_definition(
                        record.definition,
                        campaign_slug=campaign_slug,
                        systems_service=get_systems_service(),
                        martial_art_index=martial_art_index,
                        target_rank_key=request.form.get("target_rank_key", ""),
                        legendary_quest_note=request.form.get(
                            "legendary_quest_note",
                            "",
                        ),
                    )
                    definition = rank_result.definition
                    success_message = (
                        f"Spent {rank_result.insight_cost} Insight to advance "
                        f"{rank_result.martial_art_name} to {rank_result.rank_name}."
                    )
                elif cultivation_action == "learn_generic_technique":
                    redirect_anchor = "xianxia-cultivation-techniques"
                    technique_result = learn_xianxia_generic_technique_definition(
                        record.definition,
                        campaign_slug=campaign_slug,
                        systems_service=get_systems_service(),
                        generic_technique_entry_key=request.form.get(
                            "generic_technique_entry_key",
                            "",
                        ),
                        notes=request.form.get("generic_technique_notes", ""),
                    )
                    definition = technique_result.definition
                    success_message = (
                        f"Spent {technique_result.insight_cost} Insight to learn "
                        f"{technique_result.technique_name}."
                    )
                elif cultivation_action == "start_realm_ascension_review":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    realm_result = start_xianxia_realm_ascension_review_definition(
                        record.definition,
                        target_realm=request.form.get("target_realm", ""),
                        gm_review_note=request.form.get("realm_ascension_gm_review_note", ""),
                        seclusion_notes=request.form.get("realm_ascension_seclusion_notes", ""),
                        hp_stance_trade_notes=request.form.get(
                            "realm_ascension_hp_stance_trade_notes",
                            "",
                        ),
                    )
                    definition = realm_result.definition
                    success_message = (
                        f"Started Realm ascension review from {realm_result.current_realm} "
                        f"to {realm_result.target_realm}."
                    )
                elif cultivation_action == "reset_realm_ascension_stats":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    reset_result = reset_xianxia_realm_ascension_stats_definition(
                        record.definition,
                        target_realm=request.form.get("target_realm", ""),
                        notes=request.form.get("realm_ascension_reset_notes", ""),
                    )
                    definition = reset_result.definition
                    success_message = (
                        f"Reset Attributes and Efforts for {reset_result.current_realm} "
                        f"to {reset_result.target_realm} Realm ascension."
                    )
                elif cultivation_action == "apply_immortal_realm_rebuild":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    rebuild_result = apply_xianxia_immortal_realm_rebuild_definition(
                        record.definition,
                        target_realm=request.form.get("target_realm", ""),
                        attribute_scores={
                            key: request.form.get(f"realm_rebuild_attribute_{key}", "")
                            for key in XIANXIA_ATTRIBUTE_KEYS
                        },
                        effort_scores={
                            key: request.form.get(f"realm_rebuild_effort_{key}", "")
                            for key in XIANXIA_EFFORT_KEYS
                        },
                        hp_maximum_trade=request.form.get("realm_ascension_trade_hp", ""),
                        stance_maximum_trade=request.form.get(
                            "realm_ascension_trade_stance",
                            "",
                        ),
                        notes=request.form.get("realm_ascension_rebuild_notes", ""),
                    )
                    definition = rebuild_result.definition
                    success_message = (
                        f"Applied the Immortal rebuild budget for "
                        f"{rebuild_result.total_rebuild_points} points and "
                        f"{rebuild_result.actions_per_turn} actions."
                    )
                elif cultivation_action == "apply_divine_realm_rebuild":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    rebuild_result = apply_xianxia_divine_realm_rebuild_definition(
                        record.definition,
                        target_realm=request.form.get("target_realm", ""),
                        attribute_scores={
                            key: request.form.get(f"realm_rebuild_attribute_{key}", "")
                            for key in XIANXIA_ATTRIBUTE_KEYS
                        },
                        effort_scores={
                            key: request.form.get(f"realm_rebuild_effort_{key}", "")
                            for key in XIANXIA_EFFORT_KEYS
                        },
                        hp_maximum_trade=request.form.get("realm_ascension_trade_hp", ""),
                        stance_maximum_trade=request.form.get(
                            "realm_ascension_trade_stance",
                            "",
                        ),
                        notes=request.form.get("realm_ascension_rebuild_notes", ""),
                    )
                    definition = rebuild_result.definition
                    success_message = (
                        f"Applied the Divine rebuild budget for "
                        f"{rebuild_result.total_rebuild_points} points and "
                        f"{rebuild_result.actions_per_turn} actions."
                    )
                elif cultivation_action == "confirm_realm_ascension":
                    redirect_anchor = "xianxia-cultivation-realm-ascension"
                    confirmation_result = confirm_xianxia_realm_ascension_definition(
                        record.definition,
                        target_realm=request.form.get("target_realm", ""),
                        gm_confirmation_note=request.form.get(
                            "realm_ascension_gm_confirmation_note",
                            "",
                        ),
                    )
                    definition = confirmation_result.definition
                    success_message = (
                        f"Recorded GM confirmation for the "
                        f"{confirmation_result.target_realm} Realm ascension."
                    )
                else:
                    raise ValueError("Unsupported cultivation action. Refresh the page and try again.")
                definition = finalize_character_definition_for_write(
                    campaign_slug,
                    definition,
                    campaign=campaign,
                )
                import_metadata = build_managed_character_import_metadata(
                    campaign_slug,
                    record.definition.character_slug,
                    record.import_metadata,
                )
                merged_state = merge_state_with_definition(
                    definition,
                    record.state_record.state,
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
            except (CharacterStateValidationError, ValueError) as exc:
                flash(str(exc), "error")
            else:
                flash(success_message, "success")

            return redirect(
                url_for(
                    "character_xianxia_cultivation_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                    _anchor=redirect_anchor,
                )
            )

        character = present_character_detail(
            campaign,
            record,
            include_player_notes_section=True,
            systems_service=get_systems_service(),
            campaign_page_records=list_visible_character_page_records(campaign_slug, campaign),
        )
        xianxia_read = character.get("xianxia_read")
        if not isinstance(xianxia_read, dict):
            abort(404)
        generic_technique_options = []
        for option in list_xianxia_generic_technique_learning_options(
            record.definition,
            campaign_slug=campaign_slug,
            systems_service=get_systems_service(),
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

        return render_template(
            "character_cultivation_xianxia.html",
            campaign=campaign,
            character=character,
            cultivation=xianxia_cultivation.present_xianxia_cultivation_context(
                character,
                record.definition.xianxia,
                generic_technique_learning_options=generic_technique_options,
            ),
            active_nav="characters",
        )

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/progression-repair", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_progression_repair_view(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_native_character_advancement(campaign):
            return redirect_unsupported_native_character_tools(
                campaign_slug,
                character_slug=character_slug,
                message=character_advancement_unsupported_message(campaign.system),
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
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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
        level_up_readiness = native_level_up_readiness(
            get_systems_service(),
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
        item_catalog = build_character_item_catalog(campaign_slug)
        form_values = dict(request.form if request.method == "POST" else request.args)
        edit_context = build_native_character_edit_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values if request.method == "POST" else None,
            state_notes=dict((record.state_record.state or {}).get("notes") or {}),
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
            item_catalog=item_catalog,
            linked_feature_authoring_support=linked_feature_authoring,
        )
        edit_context["state_revision"] = record.state_record.revision

        if request.method != "POST":
            return render_character_edit_page(
                campaign_slug,
                character_slug,
                edit_context,
                campaign_page_records=campaign_page_records,
            )

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
                item_catalog=item_catalog,
                systems_service=app.extensions["systems_service"],
                linked_feature_authoring_support=linked_feature_authoring,
            )
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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
            character_state_store.replace_state(
                definition,
                merged_state,
                expected_revision=expected_revision,
                updated_by_user_id=user.id,
            )
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
            return render_character_edit_page(
                campaign_slug,
                character_slug,
                edit_context,
                campaign_page_records=campaign_page_records,
                status_code=409,
            )
        except (CharacterEditValidationError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_edit_page(
                campaign_slug,
                character_slug,
                edit_context,
                campaign_page_records=campaign_page_records,
                status_code=400,
            )

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
                message=character_advancement_unsupported_message(campaign.system),
            )
        level_up_readiness = native_level_up_readiness(
            get_systems_service(),
            campaign_slug,
            record.definition,
            campaign_page_records=list_builder_campaign_page_records(campaign_slug, campaign),
        )
        linked_feature_authoring = build_linked_feature_authoring_support(
            record.definition,
            readiness=level_up_readiness,
        )
        if not bool(linked_feature_authoring.get("supported")):
            flash(
                str(linked_feature_authoring.get("message") or "This character cannot use retraining yet."),
                "error",
            )
            return redirect(
                url_for(
                    "character_read_view",
                    campaign_slug=campaign_slug,
                    character_slug=character_slug,
                )
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
        item_catalog = build_character_item_catalog(campaign_slug)
        form_values = dict(request.form if request.method == "POST" else request.args)
        retraining_context = build_native_character_retraining_context(
            record.definition,
            campaign_page_records=campaign_page_records,
            form_values=form_values if request.method == "POST" else None,
            optionalfeature_catalog=optionalfeature_catalog,
            spell_catalog=spell_catalog,
            item_catalog=item_catalog,
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
                campaign_page_records=campaign_page_records,
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
                item_catalog=item_catalog,
                systems_service=app.extensions["systems_service"],
            )
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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
                campaign_page_records=campaign_page_records,
                status_code=409,
            )
        except (CharacterEditValidationError, CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return render_character_retraining_page(
                campaign_slug,
                character_slug,
                retraining_context,
                campaign_page_records=campaign_page_records,
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

    register_character_read_route(
        app,
        render_character_page=render_character_page,
    )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/controls/assignment")
    @campaign_scope_access_required("characters")
    def character_controls_assignment(campaign_slug: str, character_slug: str):
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_controls_routes(campaign):
            abort(404)
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
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_controls_routes(campaign):
            abort(404)
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
        if not campaign_supports_character_controls_routes(campaign):
            abort(404)
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
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            return jsonify(
                {
                    "results": [],
                    "message": DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE,
                }
            ), 404

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
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            return redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

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
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            return redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

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
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            return redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

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
            return build_shared_equipment_state_update_result(
                campaign_slug,
                record,
                item_id,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                values=build_equipment_state_form_values(),
            )

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-equipment-state",
            success_message="Equipment state updated.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/feature-states/<feature_key>")
    @campaign_scope_access_required("characters")
    def character_feature_state_update(campaign_slug: str, character_slug: str, feature_key: str):
        return run_character_state_mutation(
            campaign_slug,
            character_slug,
            anchor="character-equipment-state",
            success_message="Feature state updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_feature_state(
                record,
                feature_key,
                expected_revision=expected_revision,
                enabled=request.form.get("enabled") == "1",
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/equipment/<item_id>/remove")
    @campaign_scope_access_required("characters")
    def character_equipment_remove(campaign_slug: str, character_slug: str, item_id: str):
        item_catalog = build_character_item_catalog(campaign_slug)
        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="character-inventory-manager",
            success_message="Inventory item removed.",
            action=lambda record: apply_equipment_catalog_edit(
                campaign_slug,
                record.definition,
                record.import_metadata,
                item_catalog=item_catalog,
                systems_service=get_systems_service(),
                remove_item_id=item_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/xianxia/dao-immolating-use-requests")
    @campaign_scope_access_required("characters")
    def character_xianxia_dao_immolating_use_request(campaign_slug: str, character_slug: str):
        def _action(record):
            if not is_xianxia_system(getattr(record.definition, "system", "")):
                raise ValueError(
                    "Dao Immolating use requests are only available for Xianxia character sheets."
                )
            raw_prepared_record_index = request.form.get("dao_immolating_prepared_index", "")
            prepared_record_index = None
            if str(raw_prepared_record_index or "").strip():
                prepared_record_index = normalize_dm_player_wiki_int(
                    raw_prepared_record_index,
                    field_label="Prepared Dao Immolating Technique note",
                )
            request_result = request_xianxia_dao_immolating_use_definition(
                record.definition,
                request_name=request.form.get("dao_immolating_request_name", ""),
                notes=request.form.get("dao_immolating_request_notes", ""),
                prepared_record_index=prepared_record_index,
            )
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            return request_result.definition, import_metadata, {}

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-dao-immolating-use-request",
            success_message="Dao Immolating use request recorded.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/xianxia/dao-immolating-use-records")
    @campaign_scope_access_required("characters")
    def character_xianxia_dao_immolating_use_record(campaign_slug: str, character_slug: str):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        def _action(record):
            if not is_xianxia_system(getattr(record.definition, "system", "")):
                raise ValueError(
                    "Dao Immolating use records are only available for Xianxia character sheets."
                )
            raw_use_record_index = request.form.get("dao_immolating_use_index", "")
            if not str(raw_use_record_index or "").strip():
                raise ValueError("Dao Immolating Technique use selection is required.")
            use_record_index = normalize_dm_player_wiki_int(
                raw_use_record_index,
                field_label="Dao Immolating Technique use",
            )
            use_result = record_xianxia_dao_immolating_use_definition(
                record.definition,
                use_record_index=use_record_index,
                notes=request.form.get("dao_immolating_use_notes", ""),
            )
            import_metadata = build_managed_character_import_metadata(
                campaign_slug,
                record.definition.character_slug,
                record.import_metadata,
            )
            return use_result.definition, import_metadata, {}

        return run_character_definition_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-approval-dao-immolating-use-records",
            success_message="Dao Immolating one-use history recorded.",
            action=_action,
        )

    register_character_portrait_asset_route(
        app,
        load_character_context=load_character_context,
        build_character_portrait_context=build_character_portrait_context,
        get_campaign_asset_file=get_campaign_asset_file,
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
            alt_text, caption = validate_character_portrait_text(
                request.form.get("portrait_alt", ""),
                request.form.get("portrait_caption", ""),
            )

            existing_asset_ref = str((record.definition.profile or {}).get("portrait_asset_ref") or "").strip()
            next_asset_ref = build_character_portrait_asset_ref(character_slug, filename)
            definition = update_character_portrait_profile(
                record.definition,
                asset_ref=next_asset_ref,
                alt_text=alt_text,
                caption=caption,
            )
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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

        return redirect_to_character_mode(campaign_slug, character_slug, anchor="character-portrait-manager")

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
            return redirect_to_character_mode(campaign_slug, character_slug, anchor="character-portrait-manager")

        try:
            expected_revision = parse_expected_revision()
            definition = update_character_portrait_profile(record.definition)
            definition = finalize_character_definition_for_write(
                campaign_slug,
                definition,
                campaign=campaign,
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
            delete_campaign_asset_file(campaign, existing_asset_ref)
        except CharacterStateConflictError:
            flash("This sheet changed in another session. Refresh the page and try again.", "error")
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            flash("Portrait removed.", "success")

        return redirect_to_character_mode(campaign_slug, character_slug, anchor="character-portrait-manager")

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
                current_stance=request.form.get("current_stance"),
                temp_stance=request.form.get("temp_stance"),
                current_jing=request.form.get("current_jing"),
                current_qi=request.form.get("current_qi"),
                current_shen=request.form.get("current_shen"),
                current_yin=request.form.get("current_yin"),
                current_yang=request.form.get("current_yang"),
                current_dao=request.form.get("current_dao"),
                hit_dice_current=parse_hit_dice_current_values(),
                hp_delta=request.form.get("hp_delta"),
                temp_hp_delta=request.form.get("temp_hp_delta"),
                clear_temp_hp=request.form.get("clear_temp_hp") == "1",
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-active-state")
    @campaign_scope_access_required("characters")
    def character_session_xianxia_active_state(campaign_slug: str, character_slug: str):
        def update_active_state(record, expected_revision, user_id):
            return get_character_state_service().update_xianxia_active_state(
                record,
                expected_revision=expected_revision,
                active_stance_name=request.form.get("active_stance_name"),
                active_aura_name=request.form.get("active_aura_name"),
                updated_by_user_id=user_id,
            )

        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-active-state",
            success_message="Active Stance and Aura updated.",
            action=update_active_state,
        )

    def _xianxia_inventory_item_payload_from_form() -> dict[str, object]:
        tags = [
            tag.strip()
            for tag in request.form.get("tags", "").split(",")
            if tag.strip()
        ]
        payload: dict[str, object] = {
            "id": request.form.get("item_id", "").strip(),
            "name": request.form.get("name", "").strip(),
            "quantity": request.form.get("quantity", "1"),
            "item_nature": request.form.get("item_nature", XIANXIA_ITEM_NATURES[0]),
            "item_type": request.form.get("item_type", XIANXIA_ITEM_TYPES[-1]),
            "notes": request.form.get("notes", "").strip(),
            "tags": tags,
            "catalog_ref": request.form.get("catalog_ref", "").strip(),
        }
        systems_ref = {
            key: value
            for key, value in {
                "slug": request.form.get("systems_ref_slug", "").strip(),
                "entry_type": request.form.get("systems_ref_entry_type", "").strip(),
                "source_id": request.form.get("systems_ref_source_id", "").strip(),
            }.items()
            if value
        }
        if systems_ref:
            payload["systems_ref"] = systems_ref
        equippable_value = request.form.get("equippable", "").strip()
        if equippable_value:
            payload["equippable"] = equippable_value == "1"
        if "is_equipped" in request.form:
            payload["is_equipped"] = request.form.get("is_equipped") == "1"
        return payload

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
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            return redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

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

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/item-actions/<action_id>/use")
    @campaign_scope_access_required("characters")
    def character_session_item_action_use(
        campaign_slug: str,
        character_slug: str,
        action_id: str,
    ):
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)
        if not campaign_supports_dnd5e_character_spellcasting_tools(campaign):
            return redirect_unsupported_dnd5e_character_spellcasting_tools(
                campaign_slug,
                character_slug,
            )

        def _action(record, expected_revision, user_id):
            slot_lane_id, slot_level = parse_item_action_slot_selection(
                request.form.get("slot_selection")
            )
            if not slot_level:
                slot_level = int(request.form.get("slot_level") or 0)
                slot_lane_id = request.form.get("slot_lane_id", "")
            return get_character_state_service().use_spell_slot_item_action(
                record,
                resolve_projected_item_use_action(campaign_slug, campaign, record, action_id),
                choice_id=request.form.get("choice_id", ""),
                slot_level=slot_level,
                slot_lane_id=slot_lane_id,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            )

        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="character-item-use-actions",
            success_message="Item action used.",
            action=_action,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/inventory/<item_id>")
    @campaign_scope_access_required("characters")
    def character_session_inventory(
        campaign_slug: str,
        character_slug: str,
        item_id: str,
    ):
        def update_inventory(record, expected_revision, user_id):
            if is_xianxia_system(record.definition.system):
                return get_character_state_service().update_xianxia_inventory_quantity(
                    record,
                    item_id,
                    expected_revision=expected_revision,
                    quantity=request.form.get("quantity"),
                    delta=request.form.get("delta"),
                    updated_by_user_id=user_id,
                )
            return get_character_state_service().update_inventory_quantity(
                record,
                item_id,
                expected_revision=expected_revision,
                quantity=request.form.get("quantity"),
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            )

        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="session-inventory",
            success_message="Inventory updated.",
            action=update_inventory,
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/add")
    @campaign_scope_access_required("characters")
    def character_session_xianxia_inventory_add(campaign_slug: str, character_slug: str):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Inventory item added.",
            action=lambda record, expected_revision, user_id: get_character_state_service().add_xianxia_inventory_item(
                record,
                _xianxia_inventory_item_payload_from_form(),
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/update")
    @campaign_scope_access_required("characters")
    def character_session_xianxia_inventory_update(campaign_slug: str, character_slug: str, item_id: str):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Inventory item updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_xianxia_inventory_item(
                record,
                item_id,
                _xianxia_inventory_item_payload_from_form(),
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/remove")
    @campaign_scope_access_required("characters")
    def character_session_xianxia_inventory_remove(campaign_slug: str, character_slug: str, item_id: str):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Inventory item removed.",
            action=lambda record, expected_revision, user_id: get_character_state_service().remove_xianxia_inventory_item(
                record,
                item_id,
                expected_revision=expected_revision,
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/xianxia-inventory/<item_id>/equipped")
    @campaign_scope_access_required("characters")
    def character_session_xianxia_inventory_equipped(campaign_slug: str, character_slug: str, item_id: str):
        return run_session_mutation(
            campaign_slug,
            character_slug,
            anchor="xianxia-inventory",
            success_message="Equipment state updated.",
            action=lambda record, expected_revision, user_id: get_character_state_service().update_xianxia_inventory_equipped_state(
                record,
                item_id,
                expected_revision=expected_revision,
                is_equipped=request.form.get("is_equipped") == "1",
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
                values={
                    key: request.form.get(key)
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
                delta=request.form.get("delta"),
                updated_by_user_id=user_id,
            ),
        )

    @app.post("/campaigns/<campaign_slug>/characters/<character_slug>/session/notes")
    @campaign_scope_access_required("characters")
    def character_session_notes(campaign_slug: str, character_slug: str):
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        notes_markdown = request.form.get("player_notes_markdown", "")
        return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
        inactive_session_redirect = ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor="session-notes",
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect
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
            if is_session_character_return_requested(campaign_slug, character_slug):
                return render_session_character_page(
                    campaign_slug,
                    character_slug,
                    notes_draft=notes_markdown,
                    status_code=409,
                )
            return render_character_page(
                campaign_slug,
                character_slug,
                notes_draft=notes_markdown,
                force_session_mode=return_to_session_mode,
                status_code=409,
            )
        except (CharacterStateValidationError, ValueError) as exc:
            flash(str(exc), "error")
            if is_session_character_return_requested(campaign_slug, character_slug):
                return render_session_character_page(
                    campaign_slug,
                    character_slug,
                    notes_draft=notes_markdown,
                    status_code=400,
                )
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
        campaign, record = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        if not has_session_mode_access(campaign_slug, character_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        physical_description_markdown = request.form.get("physical_description_markdown", "")
        background_markdown = request.form.get("background_markdown", "")
        return_to_session_mode = request.form.get("mode", "").strip().lower() == "session"
        if is_session_character_return_requested(campaign_slug, character_slug):
            flash(
                SESSION_CHARACTER_ADVANCED_PERSONAL_EDIT_BLOCK_MESSAGE
                if campaign_supports_native_character_tools(campaign)
                else SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE,
                "error",
            )
            return redirect_to_campaign_session_character(
                campaign_slug,
                character_slug,
                anchor="session-personal-guidance",
            )
        inactive_session_redirect = ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor="session-personal",
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect
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
            if is_session_character_return_requested(campaign_slug, character_slug):
                return render_session_character_page(
                    campaign_slug,
                    character_slug,
                    physical_description_draft=physical_description_markdown,
                    background_draft=background_markdown,
                    status_code=409,
                )
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
            if is_session_character_return_requested(campaign_slug, character_slug):
                return render_session_character_page(
                    campaign_slug,
                    character_slug,
                    physical_description_draft=physical_description_markdown,
                    background_draft=background_markdown,
                    status_code=400,
                )
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
        campaign, _ = load_character_context(campaign_slug, character_slug)
        if not campaign_supports_character_session_routes(campaign):
            abort(404)
        if request.form.get("confirm_rest", "") != "1":
            return redirect_to_character_mode(campaign_slug, character_slug, anchor="session-rest")

        inactive_session_redirect = ensure_active_session_for_session_character_mutation(
            campaign_slug,
            character_slug,
            anchor="session-rest",
        )
        if inactive_session_redirect is not None:
            return inactive_session_redirect

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
