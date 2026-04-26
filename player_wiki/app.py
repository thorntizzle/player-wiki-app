from __future__ import annotations

from collections import defaultdict
from html import unescape
import hashlib
from io import BytesIO
import json
import logging
import mimetypes
from pathlib import Path
import re
import secrets
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
    can_edit_shared_systems_entries,
    can_post_campaign_session_messages,
    campaign_systems_entry_access_required,
    campaign_systems_source_access_required,
    campaign_scope_access_required,
    clear_campaign_visibility_cache,
    get_accessible_campaign_entries,
    get_auth_store,
    get_campaign_default_scope_visibility,
    get_campaign_role,
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
    _attach_campaign_item_page_support,
    _build_item_catalog,
    _normalize_equipment_payloads,
    _normalize_weapon_wield_mode_value,
    _build_spell_catalog,
    _list_campaign_enabled_entries,
    CharacterBuildError,
    apply_imported_progression_repairs,
    build_native_level_up_context,
    build_native_level_up_character_definition,
    build_imported_progression_repair_context,
    build_level_one_builder_context,
    build_level_one_character_definition,
    describe_equipment_state_support,
    normalize_definition_to_native_model,
    native_level_up_readiness,
    resolve_weapon_wield_mode,
    supports_native_level_up,
    weapon_wield_mode_label,
)
from .character_editor import (
    CharacterEditValidationError,
    apply_character_spell_management_edit,
    apply_equipment_catalog_edit,
    apply_equipment_state_edit,
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
from .campaign_combat_service import (
    CampaignCombatRevisionConflictError,
    CampaignCombatService,
    CampaignCombatValidationError,
)
from .campaign_combat_store import CampaignCombatStore
from .campaign_content_service import (
    CampaignContentError,
    delete_campaign_asset_file,
    delete_campaign_character_file,
    delete_campaign_page_file,
    get_campaign_page_file,
    list_campaign_page_files,
    write_campaign_asset_file,
    write_campaign_page_file,
)
from .campaign_dm_content_service import (
    CampaignDMContentService,
    CampaignDMContentValidationError,
    build_statblock_parser_feedback,
)
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
    SESSION_ARTICLE_SECTION_TARGETS,
    SESSION_ARTICLE_SOURCE_REF_PREFIX,
    SessionArticlePublishError,
    build_default_publish_options,
    build_session_article_source_ref,
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
from .systems_importer import Dnd5eSystemsImporter, SUPPORTED_ENTRY_TYPES
from .systems_ingest import SystemsIngestError, extracted_systems_archive
from .systems_labels import (
    SYSTEMS_ENTRY_TYPE_LABELS,
    SYSTEMS_SOURCE_INDEX_HIDDEN_ENTRY_TYPES,
    systems_entry_type_choice_labels,
    systems_entry_type_label,
    systems_entry_type_sort_key,
    systems_source_browse_intro,
)
from .systems_service import LICENSE_CLASS_LABELS, SystemsPolicyValidationError, SystemsService
from .systems_store import SystemsStore
from .system_policy import (
    DND5E_CHARACTER_SPELLCASTING_TOOLS_UNSUPPORTED_MESSAGE,
    DND_5E_SYSTEM_CODE,
    NATIVE_CHARACTER_TOOLS_UNSUPPORTED_MESSAGE,
    character_advancement_unsupported_message,
    native_character_create_unsupported_message,
    supports_character_controls_routes,
    supports_character_read_routes,
    supports_character_session_routes,
    supports_combat_tracker,
    supports_dnd5e_character_spellcasting_tools,
    supports_dnd5e_statblock_upload,
    supports_dnd5e_systems_import,
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
    "notes": "Notes",
}
CHARACTER_CONTROLS_SUBPAGE_LABELS = {
    "controls": "Controls",
}
SESSION_CHARACTER_SECTION_LABELS = {
    "overview": "Overview",
    "spells": "Spells",
    "resources": "Resources",
    "features": "Features",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "abilities_skills": "Abilities and Skills",
    "notes": "Notes",
    "personal": "Personal",
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
SESSION_CHARACTER_ACTIVE_EDIT_SCOPE = (
    "Vitals and rests on Overview",
    "Tracked resource counts and spell slot usage",
    "Inventory quantities and currency totals",
    "Player notes",
)
SESSION_CHARACTER_ACTIVE_EDIT_SUMMARY = (
    "Vitals, rests, tracked resources, spell slots, inventory quantities, currency, and player notes"
)
CHARACTER_SHEET_EDIT_FIRST_PASS_SCOPE = (
    "Current HP, temp HP, tracked resources, and spell slot usage",
    "Inventory quantities and currency totals",
    "Physical description, background, and player notes",
)
CHARACTER_SHEET_EDIT_OUTSIDE_FIRST_PASS_SCOPE = (
    "Rests and other relative quick actions",
    "Spell-list changes and other non-slot spell management",
    "Equipment state, portrait changes, and broader inventory or equipment maintenance",
    "Advanced character edit, level-up, retraining, and controls",
)
SESSION_CHARACTER_FULL_PAGE_ONLY_SCOPE = (
    "Portrait, physical description, and background details",
    "Spell-list changes and other non-slot spell management",
    "Equipment state and broader inventory or equipment maintenance",
    "Advanced character edit, level-up, retraining, and controls",
)
SESSION_CHARACTER_FULL_PAGE_ONLY_SUMMARY = (
    "Portrait/background details, spell-list changes, equipment or broader inventory work, and advanced maintenance"
)
CHARACTER_SHEET_EDIT_ACCESS_RULES = (
    "Assigned player owners can use this same sheet edit view for their own characters on the first-pass Character-page sections.",
    "DMs can open the same sheet edit view for characters they manage without reassigning ownership just to make a sheet correction.",
    "Admins can always use this sheet edit view. Owner assignment stays admin-only on Controls, and character deletion stays on Controls for DM/admin users.",
    "Observers and unassigned players stay on the standard character sheet and do not get this edit lane.",
)
COMBAT_AND_SESSION_COMBAT_SCOPE = (
    "HP, temp HP, movement, and action economy",
    "Tracked resource spends and spell slot usage",
    "Turn order and other combat-only encounter context",
)
COMBAT_AND_SESSION_COMBAT_SUMMARY = (
    "Turn-by-turn HP, movement, action economy, tracked resource spends, spell slots, and turn order"
)
COMBAT_AND_SESSION_SESSION_SCOPE = (
    "Chat, revealed articles, and wiki lookup on the main Session page",
    "Rests, inventory quantities, currency, and player notes",
    "Broader in-play character reference outside the encounter view",
)
COMBAT_AND_SESSION_SESSION_SUMMARY = (
    "the broader live-session workflow, rests, inventory quantities, currency, and player notes"
)
SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE = (
    "Portrait, physical description, and background changes stay on the full character page so "
    "this Session surface stays focused on live play."
)
SESSION_CHARACTER_PERMISSION_RULES = (
    {
        "label": "Assigned players",
        "description": "Open only their own session-enabled character here.",
    },
    {
        "label": "DMs",
        "description": "Open any session-enabled character in the campaign and use the chooser to switch sheets.",
    },
    {
        "label": "Observers",
        "description": "Stay on the main Session page and do not get a character sheet here.",
    },
    {
        "label": "Admins",
        "description": "Keep the same cross-character access as DMs.",
    },
)
SESSION_CHARACTER_PERMISSION_NOTE = (
    "Editing controls appear only during an active DM-started session and stay limited to the "
    "session-safe slice."
)
COMBAT_SUBPAGE_LABELS = {
    "combat": "Combat",
    "character": "Character",
    "status": "Encounter status",
    "dm": "Encounter controls",
}
COMBAT_SOURCE_LABELS = {
    COMBAT_SOURCE_KIND_CHARACTER: "Character",
    COMBAT_SOURCE_KIND_MANUAL_NPC: "Manual NPC",
    COMBAT_SOURCE_KIND_DM_STATBLOCK: "DM Content",
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER: "Systems",
}
COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS = {
    "actions": "Actions",
    "bonus_actions": "Bonus Actions",
    "reactions": "Reactions",
    "attacks": "Attacks",
    "spells": "Spells",
    "resources": "Resources",
    "features": "Features",
    "equipment": "Equipment",
    "inventory": "Inventory",
    "abilities_skills": "Abilities and Skills",
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
BUILDER_RELEVANT_CAMPAIGN_SECTIONS = frozenset(
    {
        CAMPAIGN_MECHANICS_SECTION,
        CAMPAIGN_ITEMS_SECTION,
    }
)
CHARACTER_PORTRAIT_ALT_MAX_LENGTH = 200
CHARACTER_PORTRAIT_CAPTION_MAX_LENGTH = 300
CHARACTER_PORTRAIT_MAX_BYTES = 8 * 1024 * 1024
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


def parse_dm_player_wiki_aliases(value: str) -> list[str]:
    aliases = []
    for line in str(value or "").replace(",", "\n").splitlines():
        alias = line.strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


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


def normalize_dm_player_wiki_page_type(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Page type is required.")
    return normalized


def build_dm_player_wiki_form(campaign, *, record=None, form_data=None) -> dict[str, object]:
    data = form_data if form_data is not None else {}
    if data:
        return {
            "title": str(data.get("title") or ""),
            "slug_leaf": str(data.get("slug_leaf") or ""),
            "section": str(data.get("section") or "Notes"),
            "page_type": str(data.get("page_type") or "note"),
            "subsection": str(data.get("subsection") or ""),
            "summary": str(data.get("summary") or ""),
            "aliases": str(data.get("aliases") or ""),
            "display_order": str(data.get("display_order") or "10000"),
            "reveal_after_session": str(data.get("reveal_after_session") or campaign.current_session),
            "source_ref": str(data.get("source_ref") or ""),
            "image": str(data.get("image") or ""),
            "image_alt": str(data.get("image_alt") or ""),
            "image_caption": str(data.get("image_caption") or ""),
            "body_markdown": str(data.get("body_markdown") or ""),
            "published": str(data.get("published") or "") == "1",
            "source_session_article_id": str(data.get("source_session_article_id") or ""),
        }

    if record is not None:
        page = record.page
        metadata = dict(record.metadata or {})
        return {
            "title": page.title,
            "slug_leaf": record.page_ref.rsplit("/", 1)[-1],
            "section": page.section,
            "page_type": page.page_type,
            "subsection": page.subsection,
            "summary": page.summary,
            "aliases": "\n".join(page.aliases),
            "display_order": str(page.display_order),
            "reveal_after_session": str(page.reveal_after_session),
            "source_ref": page.source_ref,
            "image": page.image_path,
            "image_alt": page.image_alt,
            "image_caption": page.image_caption,
            "body_markdown": record.body_markdown,
            "published": bool(metadata.get("published", page.published)),
            "source_session_article_id": "",
        }

    target = SESSION_ARTICLE_SECTION_TARGETS["Notes"]
    return {
        "title": "",
        "slug_leaf": "",
        "section": "Notes",
        "page_type": str(target["page_type"]),
        "subsection": "",
        "summary": "",
        "aliases": "",
        "display_order": "10000",
        "reveal_after_session": str(campaign.current_session),
        "source_ref": "",
        "image": "",
        "image_alt": "",
        "image_caption": "",
        "body_markdown": "",
        "published": True,
        "source_session_article_id": "",
    }


def normalize_dm_player_wiki_form(campaign, *, form_data, existing_record=None) -> tuple[str, dict[str, object], str]:
    title = str(form_data.get("title") or "").strip()
    if not title:
        raise ValueError("Wiki pages need a title.")
    if len(title) > 200:
        raise ValueError("Wiki page titles must stay under 200 characters.")

    section = str(form_data.get("section") or "").strip()
    if section not in SESSION_ARTICLE_SECTION_TARGETS:
        raise ValueError("Choose a supported wiki section.")

    page_type = normalize_dm_player_wiki_page_type(str(form_data.get("page_type") or ""))
    summary = str(form_data.get("summary") or "").strip()
    if len(summary) > 400:
        raise ValueError("Wiki page summaries must stay under 400 characters.")

    display_order = normalize_dm_player_wiki_int(
        str(form_data.get("display_order") or ""),
        field_label="Display order",
        default=10_000,
    )
    reveal_after_session = normalize_dm_player_wiki_int(
        str(form_data.get("reveal_after_session") or ""),
        field_label="Reveal after session",
        default=campaign.current_session,
    )
    body_markdown = str(form_data.get("body_markdown") or "").strip()
    published = str(form_data.get("published") or "") == "1"

    if existing_record is None:
        slug_leaf = slugify(str(form_data.get("slug_leaf") or ""))
        if not slug_leaf:
            raise ValueError("Choose a page slug before saving this wiki page.")
        target = SESSION_ARTICLE_SECTION_TARGETS[section]
        page_ref = f"{target['target_subdir']}/{slug_leaf}"
        metadata: dict[str, object] = {"slug": page_ref}
    else:
        page_ref = existing_record.page_ref
        metadata = dict(existing_record.metadata or {})
        metadata.setdefault("slug", existing_record.page.route_slug or existing_record.page_ref)

    metadata.update(
        {
            "title": title,
            "section": section,
            "type": page_type,
            "summary": summary,
            "aliases": parse_dm_player_wiki_aliases(str(form_data.get("aliases") or "")),
            "display_order": display_order,
            "reveal_after_session": reveal_after_session,
            "published": published,
        }
    )

    optional_text_fields = {
        "subsection": str(form_data.get("subsection") or "").strip(),
        "source_ref": str(form_data.get("source_ref") or "").strip(),
        "image": str(form_data.get("image") or "").strip(),
        "image_alt": str(form_data.get("image_alt") or "").strip(),
        "image_caption": str(form_data.get("image_caption") or "").strip(),
    }
    for key, value in optional_text_fields.items():
        if value:
            metadata[key] = value
        else:
            metadata.pop(key, None)

    return page_ref, metadata, body_markdown


def normalize_dm_player_wiki_image_upload(upload) -> tuple[str, bytes] | None:
    filename = Path(str(getattr(upload, "filename", "") or "").strip()).name
    if not upload or not filename:
        return None

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_SESSION_ARTICLE_IMAGE_EXTENSIONS:
        raise ValueError("Wiki page images must be PNG, JPG, GIF, or WEBP files.")

    data_blob = upload.read()
    if not data_blob:
        raise ValueError("Uploaded wiki page images cannot be empty.")
    if len(data_blob) > 8 * 1024 * 1024:
        raise ValueError("Wiki page images must stay under 8 MB.")

    return extension, data_blob


def build_dm_player_wiki_image_asset_ref(page_ref: str, extension: str) -> str:
    normalized_page_ref = slugify(page_ref).strip("/")
    if not normalized_page_ref:
        normalized_page_ref = "wiki-page"
    normalized_extension = extension if extension.startswith(".") else f".{extension}"
    return f"wiki-pages/{normalized_page_ref}{normalized_extension.lower()}"


def apply_dm_player_wiki_image_upload(campaign, page_ref: str, metadata: dict[str, object]) -> str:
    upload = request.files.get("image_file")
    normalized_upload = normalize_dm_player_wiki_image_upload(upload)
    if normalized_upload is None:
        return ""

    extension, data_blob = normalized_upload
    asset_ref = build_dm_player_wiki_image_asset_ref(page_ref, extension)
    write_campaign_asset_file(campaign, asset_ref, data_blob=data_blob)
    metadata["image"] = asset_ref
    return asset_ref


def normalize_dm_player_wiki_source_session_article_id(value: object) -> int | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        article_id = int(normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError("Session article provenance is invalid.") from exc
    if article_id <= 0:
        raise ValueError("Session article provenance is invalid.")
    return article_id


def build_dm_player_wiki_session_article_form_data(campaign, article, article_image=None) -> dict[str, object]:
    default_options = build_default_publish_options(campaign, article)
    return {
        "title": default_options.title,
        "slug_leaf": default_options.slug_leaf,
        "section": default_options.section,
        "page_type": default_options.page_type,
        "subsection": default_options.subsection,
        "summary": default_options.summary,
        "aliases": "",
        "display_order": "10000",
        "reveal_after_session": str(default_options.reveal_after_session),
        "source_ref": build_session_article_source_ref(campaign.slug, article.id),
        "image": "",
        "image_alt": article_image.alt_text if article_image is not None else "",
        "image_caption": article_image.caption if article_image is not None else "",
        "body_markdown": article.body_markdown,
        "published": "1",
        "source_session_article_id": str(article.id),
    }


def apply_dm_player_wiki_session_article_image(campaign, page_ref: str, metadata: dict[str, object], article_image) -> str:
    if article_image is None or metadata.get("image"):
        return ""

    extension = Path(article_image.filename).suffix.lower() or ".bin"
    asset_ref = build_dm_player_wiki_image_asset_ref(page_ref, extension)
    write_campaign_asset_file(campaign, asset_ref, data_blob=article_image.data_blob)
    metadata["image"] = asset_ref
    return asset_ref


def normalize_dm_player_wiki_ref_value(value: object) -> str:
    if isinstance(value, dict):
        for key in ("page_ref", "slug", "page_slug"):
            normalized = normalize_dm_player_wiki_ref_value(value.get(key))
            if normalized:
                return normalized
        return ""

    normalized = str(value or "").strip().replace("\\", "/").strip("/")
    if normalized.lower().endswith(".md"):
        normalized = normalized[:-3]
    return normalized


def collect_character_definition_page_refs(value: object) -> set[str]:
    refs: set[str] = set()

    def visit(node: object) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                normalized_key = str(key or "")
                if normalized_key == "page_ref" or normalized_key.endswith("_page_ref"):
                    normalized_ref = normalize_dm_player_wiki_ref_value(item)
                    if normalized_ref:
                        refs.add(normalized_ref)
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(value)
    return refs


def format_dm_player_wiki_usage_sample(values: list[str], *, limit: int = 3) -> str:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").split()).strip()
        normalized = cleaned.casefold()
        if not cleaned or normalized in seen:
            continue
        seen.add(normalized)
        unique_values.append(cleaned)

    if not unique_values:
        return ""

    shown = unique_values[:limit]
    label = ", ".join(shown)
    remaining = len(unique_values) - len(shown)
    if remaining > 0:
        label = f"{label}, and {remaining} more"
    return label


def build_dm_player_wiki_removal_safety_index(
    campaign_slug: str,
    campaign,
    page_records: list[object],
    *,
    session_articles: list[object],
    character_records: list[object],
) -> dict[str, dict[str, object]]:
    page_ref_lookup: defaultdict[str, set[str]] = defaultdict(set)
    link_lookup: defaultdict[str, set[str]] = defaultdict(set)
    page_titles: dict[str, str] = {}

    for record in page_records:
        page = getattr(record, "page", None)
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not page_ref or page is None:
            continue

        page_titles[page_ref] = str(getattr(page, "title", "") or page_ref).strip()
        for raw_ref in (page_ref, getattr(page, "route_slug", "")):
            normalized_ref = normalize_dm_player_wiki_ref_value(raw_ref).casefold()
            if normalized_ref:
                page_ref_lookup[normalized_ref].add(page_ref)

        for raw_key in (
            page_ref,
            getattr(page, "route_slug", ""),
            getattr(page, "title", ""),
            *list(getattr(page, "aliases", []) or []),
        ):
            normalized_key = normalize_lookup(str(raw_key or ""))
            if normalized_key:
                link_lookup[normalized_key].add(page_ref)

    backlinks_by_page_ref: defaultdict[str, list[str]] = defaultdict(list)
    for record in page_records:
        source_page = getattr(record, "page", None)
        source_page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not source_page_ref or source_page is None:
            continue

        source_title = str(getattr(source_page, "title", "") or source_page_ref).strip()
        for raw_target in list(getattr(source_page, "raw_link_targets", []) or []):
            normalized_target = normalize_lookup(str(raw_target or ""))
            for target_page_ref in sorted(link_lookup.get(normalized_target, set())):
                if target_page_ref == source_page_ref:
                    continue
                backlinks_by_page_ref[target_page_ref].append(source_title)

    character_hooks_by_page_ref: defaultdict[str, list[str]] = defaultdict(list)
    for record in page_records:
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        metadata = dict(getattr(record, "metadata", {}) or {})
        if not page_ref:
            continue
        if metadata.get("character_option"):
            character_hooks_by_page_ref[page_ref].append("character option metadata")
        if metadata.get("character_progression"):
            character_hooks_by_page_ref[page_ref].append("character progression metadata")

    for character_record in character_records:
        definition = getattr(character_record, "definition", None)
        if definition is None:
            continue
        character_name = str(getattr(definition, "name", "") or "").strip()
        if not character_name:
            character_name = str(getattr(definition, "character_slug", "") or "character").strip()
        for raw_ref in collect_character_definition_page_refs(definition.to_dict()):
            normalized_ref = normalize_dm_player_wiki_ref_value(raw_ref).casefold()
            for page_ref in sorted(page_ref_lookup.get(normalized_ref, set())):
                character_hooks_by_page_ref[page_ref].append(f"{character_name} sheet link")

    session_articles_by_id = {
        int(getattr(article, "id", 0)): article
        for article in session_articles
        if int(getattr(article, "id", 0) or 0) > 0
    }
    session_provenance_by_page_ref: defaultdict[str, list[str]] = defaultdict(list)
    for article in session_articles:
        source_kind, source_ref = parse_session_article_source_ref(
            str(getattr(article, "source_page_ref", "") or "")
        )
        if source_kind != SESSION_ARTICLE_SOURCE_KIND_PAGE:
            continue
        normalized_ref = normalize_dm_player_wiki_ref_value(source_ref).casefold()
        article_title = str(getattr(article, "title", "") or f"Article {getattr(article, 'id', '')}").strip()
        article_status = str(getattr(article, "status", "") or "").strip()
        article_label = f"{article_title} ({article_status})" if article_status else article_title
        for page_ref in sorted(page_ref_lookup.get(normalized_ref, set())):
            session_provenance_by_page_ref[page_ref].append(article_label)

    safety_index: dict[str, dict[str, object]] = {}
    for record in page_records:
        page = getattr(record, "page", None)
        page_ref = str(getattr(record, "page_ref", "") or "").strip()
        if not page_ref or page is None:
            continue

        blockers: list[str] = []
        backlink_sample = format_dm_player_wiki_usage_sample(backlinks_by_page_ref[page_ref])
        if backlink_sample:
            blockers.append(f"Backlinked from {backlink_sample}.")

        character_hook_sample = format_dm_player_wiki_usage_sample(character_hooks_by_page_ref[page_ref])
        if character_hook_sample:
            blockers.append(f"Character hooks: {character_hook_sample}.")

        source_ref = str(getattr(page, "source_ref", "") or "").strip()
        session_provenance = list(session_provenance_by_page_ref[page_ref])
        if source_ref.startswith(SESSION_ARTICLE_SOURCE_REF_PREFIX):
            source_tail = source_ref[len(SESSION_ARTICLE_SOURCE_REF_PREFIX) :].strip()
            article_label = "converted session article"
            if ":" in source_tail:
                source_campaign_slug, article_id_text = source_tail.rsplit(":", 1)
                if source_campaign_slug == campaign_slug and article_id_text.isdigit():
                    article = session_articles_by_id.get(int(article_id_text))
                    if article is not None:
                        article_status = str(getattr(article, "status", "") or "").strip()
                        article_label = str(getattr(article, "title", "") or article_label).strip()
                        if article_status:
                            article_label = f"{article_label} ({article_status})"
            session_provenance.append(article_label)

        session_sample = format_dm_player_wiki_usage_sample(session_provenance)
        if session_sample:
            blockers.append(f"Session provenance: {session_sample}.")

        can_hard_delete = not blockers
        safety_index[page_ref] = {
            "can_hard_delete": can_hard_delete,
            "hard_delete_blockers": blockers,
            "removal_status_label": "Hard delete available" if can_hard_delete else "Hard delete blocked",
            "removal_guidance": (
                "Hard delete is available after confirmation."
                if can_hard_delete
                else "Unpublish/archive this page or clear the references before deleting its file."
            ),
            "page_title": page_titles.get(page_ref, page_ref),
        }

    return safety_index


def build_dm_player_wiki_page_summary(campaign, record, *, removal_safety=None) -> dict[str, object]:
    page = record.page
    route_slug = page.route_slug
    route_page = campaign.pages.get(route_slug)
    is_visible = campaign.is_page_visible(route_page or page)
    removal_safety = dict(removal_safety or {})
    search_text = " ".join(
        str(part or "")
        for part in (
            record.page_ref,
            page.title,
            page.section,
            page.subsection,
            page.page_type,
            page.summary,
            page.source_ref,
        )
    ).lower()
    status_label = (
        "Visible"
        if is_visible
        else "Unpublished"
        if not page.published
        else f"Reveals after session {page.reveal_after_session}"
    )
    return {
        "page_ref": record.page_ref,
        "dom_id": re.sub(r"[^a-zA-Z0-9_-]+", "-", record.page_ref).strip("-") or "page",
        "title": page.title,
        "section": page.section,
        "subsection": page.subsection,
        "page_type": page.page_type,
        "summary": page.summary,
        "source_ref": page.source_ref,
        "image_path": page.image_path,
        "published": page.published,
        "is_visible": is_visible,
        "status_label": status_label,
        "route_slug": route_slug,
        "search_text": search_text,
        "can_hard_delete": bool(removal_safety.get("can_hard_delete", True)),
        "hard_delete_blockers": list(removal_safety.get("hard_delete_blockers", []) or []),
        "removal_status_label": str(removal_safety.get("removal_status_label") or "Hard delete available"),
        "removal_guidance": str(removal_safety.get("removal_guidance") or "Hard delete is available after confirmation."),
    }


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
        "visibility": "players",
        "provenance": "",
        "search_metadata": "",
        "body_markdown": "",
    }


def custom_systems_entry_dom_id(entry) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(entry.slug or entry.id)).strip("-") or "custom-entry"


def format_systems_entry_json_field(value) -> str:
    if not value:
        return "{}"
    return json.dumps(value, indent=2, sort_keys=True)


def build_shared_systems_entry_form(*, entry=None, form_data=None) -> dict[str, object]:
    data = form_data if form_data is not None else {}
    if data:
        return {
            "title": str(data.get("shared_entry_title") or ""),
            "source_page": str(data.get("shared_entry_source_page") or ""),
            "source_path": str(data.get("shared_entry_source_path") or ""),
            "search_text": str(data.get("shared_entry_search_text") or ""),
            "player_safe_default": data.get("shared_entry_player_safe_default") == "1",
            "dm_heavy": data.get("shared_entry_dm_heavy") == "1",
            "metadata_json": str(data.get("shared_entry_metadata_json") or "{}"),
            "body_json": str(data.get("shared_entry_body_json") or "{}"),
            "rendered_html": str(data.get("shared_entry_rendered_html") or ""),
            "mechanics_impact_acknowledged": (
                data.get("shared_entry_mechanics_impact_acknowledged") == "1"
            ),
        }
    if entry is not None:
        return {
            "title": entry.title,
            "source_page": entry.source_page,
            "source_path": entry.source_path,
            "search_text": entry.search_text,
            "player_safe_default": bool(entry.player_safe_default),
            "dm_heavy": bool(entry.dm_heavy),
            "metadata_json": format_systems_entry_json_field(entry.metadata),
            "body_json": format_systems_entry_json_field(entry.body),
            "rendered_html": entry.rendered_html,
            "mechanics_impact_acknowledged": False,
        }
    return {
        "title": "",
        "source_page": "",
        "source_path": "",
        "search_text": "",
        "player_safe_default": False,
        "dm_heavy": False,
        "metadata_json": "{}",
        "body_json": "{}",
        "rendered_html": "",
        "mechanics_impact_acknowledged": False,
    }


def build_shared_systems_entry_original_source_identity(entry) -> dict[str, object]:
    return {
        "library_slug": entry.library_slug,
        "source_id": entry.source_id,
        "entry_key": entry.entry_key,
        "entry_slug": entry.slug,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "source_page": entry.source_page,
        "source_path": entry.source_path,
    }


def list_shared_systems_entry_changed_fields(before_entry, after_entry) -> list[str]:
    comparable_fields = {
        "title": (before_entry.title, after_entry.title),
        "source_page": (before_entry.source_page, after_entry.source_page),
        "source_path": (before_entry.source_path, after_entry.source_path),
        "search_text": (before_entry.search_text, after_entry.search_text),
        "player_safe_default": (bool(before_entry.player_safe_default), bool(after_entry.player_safe_default)),
        "dm_heavy": (bool(before_entry.dm_heavy), bool(after_entry.dm_heavy)),
        "metadata": (dict(before_entry.metadata or {}), dict(after_entry.metadata or {})),
        "body": (dict(before_entry.body or {}), dict(after_entry.body or {})),
        "rendered_html": (before_entry.rendered_html, after_entry.rendered_html),
    }
    return [field for field, (before_value, after_value) in comparable_fields.items() if before_value != after_value]


def parse_shared_systems_entry_json_field(raw_value: str, *, field_label: str) -> dict[str, object]:
    cleaned_value = str(raw_value or "").strip()
    if not cleaned_value:
        return {}
    try:
        parsed = json.loads(cleaned_value)
    except json.JSONDecodeError as exc:
        raise SystemsPolicyValidationError(f"{field_label} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise SystemsPolicyValidationError(f"{field_label} must be a JSON object.")
    return parsed


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


def get_session_character_subpage_labels(
    *,
    include_spellcasting: bool = False,
) -> dict[str, str]:
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
) -> str:
    allowed_labels = get_session_character_subpage_labels(
        include_spellcasting=include_spellcasting
    )
    normalized = normalize_lookup(value)
    candidate = SESSION_CHARACTER_SECTION_ALIASES.get(normalized, "")
    if candidate in allowed_labels:
        return candidate
    return "overview"


def normalize_combat_return_view(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"dm", "status"}:
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
            "path": request.full_path.rstrip("?"),
            "endpoint": str(request.endpoint or ""),
            "query_count": int(query_metrics["query_count"] or 0),
            "query_time_ms": round(float(query_metrics["query_time_ms"] or 0.0), 2),
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
            payload["exception"] = str(exception)
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

    before_request_chain = app.before_request_funcs.setdefault(None, [])
    if before_request_chain and before_request_chain[-1] is initialize_request_diagnostics:
        before_request_chain.insert(0, before_request_chain.pop())

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
            for page_record in get_campaign_page_store().list_page_records(campaign_slug, include_body=True)
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

    def build_character_item_catalog(campaign_slug: str) -> dict[str, object]:
        return _attach_campaign_item_page_support(
            _build_item_catalog(
                _list_campaign_enabled_entries(
                    get_systems_service(),
                    campaign_slug,
                    "item",
                )
            ),
            [
                page_record
                for page_record in get_campaign_page_store().list_page_records(campaign_slug, include_body=True)
                if str(getattr(getattr(page_record, "page", None), "section", "") or "").strip() == CHARACTER_ITEMS_SECTION
            ],
        )

    def build_record_equipment_support_lookup(
        record,
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
                    "href": build_character_entry_href(
                        campaign.slug,
                        systems_ref=systems_ref,
                        page_ref=definition_item.get("page_ref"),
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
            "active_interval_ms": 500,
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

    def parse_expected_combatant_revision() -> int | None:
        raw_value = request.form.get("expected_combatant_revision", "").strip()
        if not raw_value:
            return None
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
    ) -> str:
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

    def build_session_character_access_summary(
        campaign_slug: str,
        *,
        can_manage_session: bool,
        accessible_records: list[object],
    ) -> str:
        current_user = get_current_user()
        role = get_campaign_role(campaign_slug)
        if current_user is not None and current_user.is_admin:
            return (
                "Current access: admin cross-character access. You can open any "
                "session-enabled character here."
            )
        if can_manage_session:
            return (
                "Current access: DM cross-character access. You can open any "
                "session-enabled character here."
            )
        if accessible_records:
            return (
                "Current access: assigned-player access. This page stays scoped to your "
                "own session-enabled character."
            )
        if role == "observer":
            return (
                "Current access: observers stay on the main Session page and do not get a "
                "session character sheet."
            )
        if role == "player":
            return "Current access: no session-enabled character is assigned to this account yet."
        return "Current access: only assigned players, DMs, and admins can open this surface."

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
    ) -> dict[str, str]:
        route_values = build_combat_route_values(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
        )
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

    def build_help_surface(
        *,
        anchor: str,
        label: str,
        summary: str,
        status_label: str,
        access_note: str,
        capabilities: list[str],
        limits: list[str],
        links: list[dict[str, str]] | None = None,
        guidance_cards: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "anchor": anchor,
            "label": label,
            "summary": summary,
            "status_label": status_label,
            "access_note": access_note,
            "capabilities": capabilities,
            "limits": limits,
            "links": list(links or []),
            "guidance_cards": list(guidance_cards or []),
        }

    def format_help_label_list(labels: list[str]) -> str:
        normalized_labels = [str(label).strip() for label in labels if str(label).strip()]
        if not normalized_labels:
            return ""
        if len(normalized_labels) == 1:
            return normalized_labels[0]
        if len(normalized_labels) == 2:
            return f"{normalized_labels[0]} and {normalized_labels[1]}"
        return f"{', '.join(normalized_labels[:-1])}, and {normalized_labels[-1]}"

    def build_campaign_help_viewer_context(campaign_slug: str) -> dict[str, str]:
        current_user = get_current_user()
        role = get_campaign_role(campaign_slug)
        if current_user is not None and current_user.is_admin:
            return {
                "role_label": "Admin",
                "role_summary": (
                    "Admins can open every campaign surface even when the normal visibility "
                    "floor would hide it for other viewers."
                ),
            }
        if role == "dm":
            return {
                "role_label": "Dungeon Master",
                "role_summary": (
                    "DMs can use the player-facing surfaces plus campaign management routes "
                    "such as Session DM, Encounter status, Encounter controls, DM Content, "
                    "and Control."
                ),
            }
        if role == "player":
            return {
                "role_label": "Player",
                "role_summary": (
                    "Players can use the currently visible campaign surfaces, but write "
                    "actions stay limited to the character and encounter workflows the app "
                    "explicitly allows."
                ),
            }
        if role == "observer":
            return {
                "role_label": "Observer",
                "role_summary": (
                    "Observers can read only the surfaces whose current visibility allows "
                    "them, while live posting and GM management stay disabled."
                ),
            }
        if current_user is not None:
            return {
                "role_label": "Signed-in visitor",
                "role_summary": (
                    "This account does not currently have an active membership in this "
                    "campaign, so only the public surfaces are available."
                ),
            }
        return {
            "role_label": "Public visitor",
            "role_summary": (
                "You are viewing the public portion of this campaign. Member-only surfaces "
                "stay hidden until you sign in with the right campaign access."
            ),
        }

    def build_campaign_help_context(campaign_slug: str) -> dict[str, object]:
        campaign = load_campaign_context(campaign_slug)
        viewer_context = build_campaign_help_viewer_context(campaign_slug)
        current_user = get_current_user()

        wiki_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "wiki")]
        systems_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "systems")]
        session_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "session")]
        combat_visibility_label = VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, "combat")]
        dm_content_visibility_label = VISIBILITY_LABELS[
            get_effective_campaign_visibility(campaign_slug, "dm_content")
        ]
        characters_visibility_label = VISIBILITY_LABELS[
            get_effective_campaign_visibility(campaign_slug, "characters")
        ]

        can_view_wiki = can_access_campaign_scope(campaign_slug, "wiki")
        can_view_systems = can_access_campaign_scope(campaign_slug, "systems")
        can_view_session = can_access_campaign_scope(campaign_slug, "session")
        can_view_combat = can_access_campaign_scope(campaign_slug, "combat")
        can_view_dm_content = can_access_campaign_scope(campaign_slug, "dm_content")
        can_view_characters = can_access_campaign_scope(campaign_slug, "characters")

        can_manage_systems = can_manage_campaign_systems(campaign_slug)
        can_manage_session = can_manage_campaign_session(campaign_slug)
        can_manage_combat = can_manage_campaign_combat(campaign_slug)
        can_manage_visibility = can_manage_campaign_visibility(campaign_slug)

        native_character_tools_supported = campaign_supports_native_character_tools(campaign)
        combat_system_supported = supports_combat_tracker(campaign.system)
        system_label = str(getattr(campaign, "system", "") or "").strip() or "Unspecified"
        combat_source_seed_capability = (
            "NPC combatants can be seeded from Systems monsters and DM Content statblocks when those source libraries are available."
        )
        if can_view_systems and not can_view_dm_content:
            combat_source_seed_capability = (
                "Systems monsters can seed NPC combatants when that library is available to this viewer."
            )
        elif can_view_dm_content and not can_view_systems:
            combat_source_seed_capability = (
                "DM Content statblocks can seed NPC combatants when that library is available to this viewer."
            )
        elif not can_view_systems and not can_view_dm_content:
            combat_source_seed_capability = (
                "NPC combatants can be added from linked source libraries when those sources are available to this viewer."
            )
        character_guidance_cards: list[dict[str, object]] = [
            {
                "title": "Sheet edit view",
                "body": "Use the out-of-session Character page sheet edit view for the first-pass fields that stay local until you save or cancel them.",
                "items": list(CHARACTER_SHEET_EDIT_FIRST_PASS_SCOPE),
                "meta": "This lane batches one page-local draft through sheet-edit instead of applying immediate Session or Combat deltas.",
            },
            {
                "title": "Keep the full character page for",
                "body": "",
                "items": list(CHARACTER_SHEET_EDIT_OUTSIDE_FIRST_PASS_SCOPE),
                "meta": "",
            },
        ]
        if can_view_session:
            character_guidance_cards.append(
                {
                    "title": "Session Character",
                    "body": "Use Session Character during an active session when you need live-play edits without leaving the Session feature.",
                    "items": list(SESSION_CHARACTER_ACTIVE_EDIT_SCOPE),
                    "meta": (
                        "Keep the full character page for "
                        f"{SESSION_CHARACTER_FULL_PAGE_ONLY_SUMMARY.lower()}."
                    ),
                }
            )
        if can_view_combat:
            character_guidance_cards.append(
                {
                    "title": "Combat",
                    "body": "Use Combat when the character is in the tracker and encounter context matters.",
                    "items": list(COMBAT_AND_SESSION_COMBAT_SCOPE),
                    "meta": f"Keep Session for {COMBAT_AND_SESSION_SESSION_SUMMARY}.",
                }
            )
        character_guidance_cards.extend(
            [
                {
                    "title": "Who can use sheet edit view",
                    "body": "",
                    "items": list(CHARACTER_SHEET_EDIT_ACCESS_RULES),
                    "meta": "",
                },
                {
                    "title": "Compatibility note",
                    "body": (
                        "Older Character-page links that still use ?mode=session open this same sheet edit view. "
                        "The user-facing label stays Sheet edit view so the compatibility route does not keep "
                        "teaching an old Session-only label."
                    ),
                    "items": [],
                    "meta": "",
                },
            ]
        )

        help_surfaces = [
            build_help_surface(
                anchor="campaign-home",
                label="Campaign Home",
                summary="Published player-facing wiki hub and header search.",
                status_label="Open" if can_view_wiki else "Limited",
                access_note=(
                    f"You can browse published wiki content here. Current Wiki visibility: {wiki_visibility_label}."
                    if can_view_wiki
                    else (
                        "You can still open the campaign shell, but published wiki browsing "
                        f"currently requires {wiki_visibility_label} access."
                    )
                ),
                capabilities=[
                    "Browse published sections and article pages from the campaign hub.",
                    "Use the header search to match titles, aliases, summaries, and page body text.",
                    "Treat this as the safest player-facing starting point for campaign reference.",
                ],
                limits=[
                    "Only published player-safe content appears here.",
                    "GM vault notes, Inbox drafts, and other unpublished material do not surface here.",
                    "This route is read-only; publishing and reveal timing happen on other surfaces.",
                ],
                links=[
                    {
                        "label": "Open Campaign Home",
                        "href": url_for("campaign_view", campaign_slug=campaign.slug),
                    }
                ],
            ),
            build_help_surface(
                anchor="systems",
                label="Systems",
                summary="Shared mechanics library for rules, creatures, spells, items, and other imported entries.",
                status_label="Open" if can_view_systems else "Hidden",
                access_note=(
                    (
                        f"You can open Systems right now. Current Systems visibility: {systems_visibility_label}."
                        + (
                            " You can also adjust source visibility from Systems Policy."
                            if can_manage_systems
                            else ""
                        )
                    )
                    if can_view_systems
                    else f"Systems currently requires {systems_visibility_label} access."
                ),
                capabilities=[
                    "Browse enabled sources and categories without loading the whole rules library at once.",
                    "Open linked mechanics from character sheets, combat sources, and campaign overlays.",
                    "Use Rules Reference Search for chapter headings, aliases, formulas, and other curated rule metadata.",
                ],
                limits=[
                    "Systems is currently a DND-5E-first shared library.",
                    "Global Systems search matches title, entry type, and source rather than full body text.",
                    "Rules Reference Search is metadata-driven instead of generic body-text search.",
                ],
                links=(
                    [
                        {
                            "label": "Open Systems",
                            "href": url_for("campaign_systems_index", campaign_slug=campaign.slug),
                        }
                    ]
                    + (
                        [
                            {
                                "label": "Open Systems Policy",
                                "href": url_for(
                                    "campaign_systems_control_panel_view",
                                    campaign_slug=campaign.slug,
                                ),
                            }
                        ]
                        if can_manage_systems
                        else []
                    )
                ),
            ),
            build_help_surface(
                anchor="session",
                label="Session",
                summary="Live play surface for chat, revealed articles, and in-session lookup.",
                status_label="Open" if can_view_session else "Hidden",
                access_note=(
                    (
                        f"You can open Session right now. Current Session visibility: {session_visibility_label}."
                        + (
                            " This viewer can post chat during an active session."
                            if can_post_campaign_session_messages(campaign_slug)
                            else " This viewer can read the surface but cannot post live chat messages."
                        )
                    )
                    if can_view_session
                    else f"Session currently requires {session_visibility_label} access."
                ),
                capabilities=[
                    "Follow the live session feed for chat and DM-revealed articles.",
                    "Use the wiki lookup widget to preview player-visible published pages without leaving Session.",
                    (
                        "DMs can stage manual, upload, or wiki-backed articles, reveal them live, and convert session-only content into published wiki pages."
                        if can_manage_session
                        else "Assigned players, DMs, and admins can use the separate Session Character surface for in-play sheet access while chat and article tools stay on the main Session page."
                    ),
                ],
                limits=[
                    "Live updates use lightweight polling rather than websockets.",
                    "Session-only articles stay out of the published wiki and search until a DM converts them.",
                    "The Session Character surface intentionally keeps a smaller in-play slice than the full character page.",
                ],
                links=(
                    [
                        {
                            "label": "Open Session",
                            "href": url_for("campaign_session_view", campaign_slug=campaign.slug),
                        }
                    ]
                    + (
                        [
                            {
                                "label": "Open DM Page",
                                "href": url_for(
                                    "campaign_session_dm_view",
                                    campaign_slug=campaign.slug,
                                ),
                            }
                        ]
                        if can_manage_session
                        else []
                    )
                ),
            ),
            build_help_surface(
                anchor="combat",
                label="Combat",
                summary="Encounter tracker and in-combat character workspace.",
                status_label=(
                    "Open"
                    if can_view_combat and combat_system_supported
                    else "Limited"
                    if can_view_combat
                    else "Hidden"
                ),
                access_note=(
                    (
                        f"You can open Combat right now. Current Combat visibility: {combat_visibility_label}."
                        + (
                            ""
                            if combat_system_supported
                            else f" This campaign uses {system_label}, so combat stays limited until non-{DND_5E_SYSTEM_CODE} support exists."
                        )
                    )
                    if can_view_combat
                    else f"Combat currently requires {combat_visibility_label} access."
                ),
                capabilities=[
                    "Track turn order, HP, conditions, movement, and encounter state during play.",
                    (
                        "DMs split encounter work between Encounter status for selected-combatant state and Encounter controls for setup, seeding, structural edits, and cleanup."
                        if can_manage_combat
                        else "Players with a tracked combatant get a character-first workspace on the main Combat surface instead of only a tracker readout."
                    ),
                    combat_source_seed_capability,
                ],
                limits=[
                    f"Combat is currently implemented for {DND_5E_SYSTEM_CODE} campaigns.",
                    "Player edits stay limited to their own allowed combat-facing character state.",
                    "NPC detail visibility remains DM-controlled.",
                ],
                links=(
                    [
                        {
                            "label": "Open Combat",
                            "href": url_for("campaign_combat_view", campaign_slug=campaign.slug),
                        }
                    ]
                    + (
                        [
                            {
                                "label": "Open Encounter Status",
                                "href": url_for(
                                    "campaign_combat_status_view",
                                    campaign_slug=campaign.slug,
                                ),
                            },
                            {
                                "label": "Open Encounter Controls",
                                "href": url_for(
                                    "campaign_combat_dm_view",
                                    campaign_slug=campaign.slug,
                                ),
                            },
                        ]
                        if can_manage_combat
                        else []
                    )
                ),
            ),
            build_help_surface(
                anchor="dm-content",
                label="DM Content",
                summary=(
                    "DM-facing content management for player wiki pages, Systems policy and custom entries, "
                    "statblocks, staged articles, and custom conditions."
                ),
                status_label=(
                    "Open"
                    if can_view_dm_content and combat_system_supported
                    else "Limited"
                    if can_view_dm_content
                    else "Hidden"
                ),
                access_note=(
                    (
                        f"You can open DM Content right now. Current DM Content visibility: {dm_content_visibility_label}."
                        + (
                            ""
                            if combat_system_supported
                            else f" Statblock upload is currently built only for {DND_5E_SYSTEM_CODE} campaigns."
                        )
                    )
                    if can_view_dm_content
                    else f"DM Content currently requires {dm_content_visibility_label} access."
                ),
                capabilities=[
                    "Create, edit, attach images to, unpublish/archive, or safely hard-delete player wiki Markdown pages from the Player Wiki lane.",
                    "Manage Systems source enablement, entry overrides, custom campaign entries, shared-source import review, and admin-only DND-5E ZIP imports from the Systems lane.",
                    "Upload and edit DM statblock markdown for later encounter seeding.",
                    "Prepare and revise unrevealed staged session articles before reveal or wiki publication.",
                    "Maintain custom combat conditions alongside the built-in DND-5E list.",
                ],
                limits=[
                    "Player wiki edits still need normal spoiler and reveal-safety judgment before publication.",
                    "Inline wiki-page image uploads are copied into campaign assets and referenced from page frontmatter.",
                    "Hard delete is blocked when a page still has wiki backlinks, character hooks, or session provenance.",
                    "Imported shared-library Systems entries are not edited through campaign management; the shared/core editor is reserved for app admins and kept separate from source policy, entry overrides, and custom campaign entries.",
                    "The statblock parser is currently implemented for DND-5E-style markdown.",
                    "Statblock saves need recognizable Armor Class, Hit Points, and Speed lines when those values should feed Combat.",
                    "Custom conditions augment the built-in list rather than replacing it.",
                ],
                links=(
                    [
                        {
                            "label": "Open DM Content",
                            "href": url_for("campaign_dm_content_view", campaign_slug=campaign.slug),
                        },
                        {
                            "label": "Open Player Wiki",
                            "href": url_for(
                                "campaign_dm_content_subpage_view",
                                campaign_slug=campaign.slug,
                                dm_content_subpage="player-wiki",
                            ),
                        },
                        {
                            "label": "Open Systems",
                            "href": url_for(
                                "campaign_dm_content_subpage_view",
                                campaign_slug=campaign.slug,
                                dm_content_subpage="systems",
                            ),
                        },
                        {
                            "label": "Open Staged Articles",
                            "href": url_for(
                                "campaign_dm_content_subpage_view",
                                campaign_slug=campaign.slug,
                                dm_content_subpage="staged-articles",
                            ),
                        }
                    ]
                    if can_view_dm_content
                    else []
                ),
                guidance_cards=[
                    {
                        "title": "Browser and API boundary",
                        "body": "",
                        "items": [
                            "Browser Player Wiki saves use the content service so mirrored Markdown and the read model stay synchronized.",
                            "Browser Player Wiki hard delete adds usage checks before the low-level content delete runs.",
                            "The raw content API remains available for automation, but API clients need their own publish-safety and dependency checks.",
                        ],
                        "meta": "",
                    },
                    {
                        "title": "Character-linked content",
                        "body": "",
                        "items": [
                            "Player Wiki deletion checks include character hooks and sheet page references.",
                            "Character file API management is separate from native character create, edit, level-up, repair, and controls workflows.",
                        ],
                        "meta": "",
                    },
                ],
            ),
            build_help_surface(
                anchor="characters",
                label="Characters",
                summary="Full read-mode character sheets plus the broader maintenance surface.",
                status_label=(
                    "Open"
                    if can_view_characters and native_character_tools_supported
                    else "Limited"
                    if can_view_characters
                    else "Hidden"
                ),
                access_note=(
                    (
                        f"You can open Characters right now. Current Characters visibility: {characters_visibility_label}."
                        + (
                            " Native create/edit/level-up tools are available for this campaign system."
                            if native_character_tools_supported
                            else f" Native authoring stays limited because this campaign is not using {DND_5E_SYSTEM_CODE}."
                        )
                    )
                    if can_view_characters
                    else f"Characters currently requires {characters_visibility_label} access."
                ),
                capabilities=[
                    "Browse full character sheets and their read-mode subpages.",
                    (
                        "Use native DND-5E create, edit, level-up, and progression-repair flows where your role allows them."
                        if native_character_tools_supported
                        else "Use read-mode, Session Character, and combat-linked views for character reference even though native authoring is unavailable here."
                    ),
                    "Use the full character page for portraits, equipment state, spell-list maintenance, and broader sheet upkeep.",
                ],
                limits=[
                    f"Native authoring tools are currently only supported for {DND_5E_SYSTEM_CODE} campaigns.",
                    "Imported characters may need progression repair before native level-up is available.",
                    "Session and Combat intentionally keep only a smaller quick-edit slice instead of replacing the full character page.",
                ],
                guidance_cards=character_guidance_cards,
                links=(
                    [
                        {
                            "label": "Open Characters",
                            "href": url_for("character_roster_view", campaign_slug=campaign.slug),
                        }
                    ]
                    if can_view_characters
                    else []
                ),
            ),
            build_help_surface(
                anchor="control",
                label="Control",
                summary="Visibility management for the campaign and each campaign-owned scope.",
                status_label="Open" if can_manage_visibility else "Hidden",
                access_note=(
                    "You can open Control because this viewer can manage campaign visibility."
                    if can_manage_visibility
                    else "Only the campaign DM or an admin can open this surface."
                ),
                capabilities=[
                    "Set the campaign-wide visibility floor and the per-scope defaults for wiki, systems, session, combat, DM Content, and characters.",
                    "Review the effective visibility each scope currently resolves to.",
                    "Use this page to decide which surfaces are public, player-visible, DM-only, or private.",
                ],
                limits=[
                    "The more private value between Campaign and an individual scope wins.",
                    "`Private` is reserved for admins.",
                    "Changing visibility does not rewrite content; it only changes who can see the route.",
                ],
                links=(
                    [
                        {
                            "label": "Open Control",
                            "href": url_for(
                                "campaign_control_panel_view",
                                campaign_slug=campaign.slug,
                            ),
                        }
                    ]
                    if can_manage_visibility
                    else []
                ),
            ),
        ]

        visible_help_surfaces = [
            surface for surface in help_surfaces if surface["status_label"] in {"Open", "Limited"}
        ]

        visibility_rows = []
        for scope in CAMPAIGN_VISIBILITY_SCOPES:
            viewer_can_open = can_access_campaign_scope(campaign_slug, scope)
            if not viewer_can_open:
                continue
            visibility_rows.append(
                {
                    "label": CAMPAIGN_VISIBILITY_SCOPE_LABELS[scope],
                    "visibility_label": VISIBILITY_LABELS[get_effective_campaign_visibility(campaign_slug, scope)],
                    "viewer_can_open": viewer_can_open,
                }
            )

        available_surface_labels = [
            surface["label"]
            for surface in visible_help_surfaces
        ]

        help_cross_cutting_limits = [
            "Campaign visibility can hide a feature even when the route exists for other roles.",
        ]

        dnd5e_first_features: list[str] = []
        if can_view_characters:
            dnd5e_first_features.append("native character authoring")
        if can_view_combat:
            dnd5e_first_features.append("combat")
        if can_view_dm_content:
            dnd5e_first_features.append("DM Content statblocks")
        if can_view_combat and can_view_systems:
            dnd5e_first_features.append("Systems-backed combat seeding")
        if dnd5e_first_features:
            help_cross_cutting_limits.append(
                f"{format_help_label_list(dnd5e_first_features)} {'is' if len(dnd5e_first_features) == 1 else 'are'} currently DND-5E-first workflow{'s' if len(dnd5e_first_features) != 1 else ''}."
            )

        if can_view_systems:
            help_cross_cutting_limits.append(
                "Systems search is intentionally narrow: global search matches title, type, and source, while Rules Reference Search uses metadata."
            )

        if can_view_session or can_view_combat:
            live_surfaces: list[str] = []
            if can_view_session:
                live_surfaces.append("Session")
            if can_view_combat:
                live_surfaces.append("Combat")
            help_cross_cutting_limits.append(
                f"{format_help_label_list(live_surfaces)} refresh{'es' if len(live_surfaces) == 1 else ''} with polling instead of websockets."
            )

        if can_view_session and can_manage_session:
            help_cross_cutting_limits.append(
                "Session-only articles stay separate from the published wiki until a DM converts them."
            )

        return {
            "campaign": campaign,
            "help_surfaces": visible_help_surfaces,
            "help_viewer_role_label": viewer_context["role_label"],
            "help_viewer_role_summary": viewer_context["role_summary"],
            "help_campaign_system_label": system_label,
            "help_available_surface_labels": available_surface_labels,
            "help_cross_cutting_limits": help_cross_cutting_limits,
            "help_visibility_rows": visibility_rows,
            "help_account_note": (
                "Account settings let signed-in users change their color theme and preferred live Session chat order."
                if current_user is not None
                else "Sign in to save theme preferences, choose a live Session chat order, and open member-only surfaces."
            ),
            "active_nav": "help",
        }

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
            can_manage_character
            and level_up_readiness
            and level_up_readiness.get("status") == "ready"
        )
        can_prepare_level_up = bool(
            can_manage_character
            and level_up_readiness
            and level_up_readiness.get("status") == "repairable"
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
        character_session_surface_href = ""
        if (
            is_session_mode
            and get_campaign_session_service().get_active_session(campaign_slug) is not None
            and can_access_session_character_surface(campaign_slug, character_slug)
        ):
            character_session_surface_href = url_for(
                "campaign_session_character_view",
                campaign_slug=campaign.slug,
                character=character_slug,
                page=CHARACTER_READ_TO_SESSION_CHARACTER_PAGE_MAP.get(
                    character_subpage,
                    "overview",
                ),
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

        if str(request.form.get("combat_view") or "").strip().lower() == "combat":
            return redirect_to_campaign_combat(
                campaign_slug,
                combatant_id=combatant_id,
                anchor=anchor,
            )

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
        accessible_session_character_records = list_session_accessible_character_records(campaign_slug)
        show_session_character_tab = bool(accessible_session_character_records)
        default_session_character_slug = get_default_session_character_slug(
            campaign_slug,
            accessible_records=accessible_session_character_records,
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
            "session_live_revision": session_live_revision,
            "session_live_view_token": session_live_view_token,
            "live_diagnostics_enabled": app.config["LIVE_DIAGNOSTICS"],
            "session_poll_active_interval_ms": session_poll_settings["active_interval_ms"],
            "session_poll_idle_interval_ms": session_poll_settings["idle_interval_ms"],
            "session_poll_idle_threshold_ms": session_poll_settings["idle_threshold_ms"],
            "session_subpage": normalized_session_subpage,
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
            "active_nav": "session",
        }

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
                    data_blob=markdown_file.read() if markdown_file is not None else b"",
                )
                article = session_service.create_article(
                    campaign_slug,
                    title=markdown_upload.title,
                    body_markdown=markdown_upload.body_markdown,
                    created_by_user_id=created_by_user_id,
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
                        updated_by_user_id=created_by_user_id,
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
                        created_by_user_id=created_by_user_id,
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
                        created_by_user_id=created_by_user_id,
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
                                updated_by_user_id=created_by_user_id,
                            )
            else:
                article = session_service.create_article(
                    campaign_slug,
                    title=request.form.get("title", ""),
                    body_markdown=request.form.get("body_markdown", ""),
                    created_by_user_id=created_by_user_id,
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

        updated_article = session_service.update_article(
            campaign_slug,
            article_id,
            title=request.form.get("title", ""),
            body_markdown=request.form.get("body_markdown", ""),
            updated_by_user_id=updated_by_user_id,
        )
        if image_file is not None and image_filename:
            session_service.attach_article_image(
                campaign_slug,
                article_id,
                filename=image_filename,
                media_type=image_file.mimetype,
                data_blob=image_file.read(),
                alt_text=image_alt,
                caption=image_caption,
                updated_by_user_id=updated_by_user_id,
            )
        elif session_service.get_article_image(campaign_slug, article_id) is not None:
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
            live_messages = session_service.list_messages(active_session_record.id)
            active_session = present_session_record(
                active_session_record,
                message_count=len(live_messages),
            )

        requested_character_slug = (
            str(selected_character_slug).strip()
            if selected_character_slug is not None
            else request.args.get("character", "").strip()
        )
        if requested_character_slug and requested_character_slug not in accessible_records_by_slug:
            abort(403)
        selected_character_slug = requested_character_slug or (
            get_default_session_character_slug(
                campaign_slug,
                accessible_records=accessible_records,
            )
            or ""
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
        session_personal_editing_enabled = False
        session_personal_edit_block_message = ""
        session_personal_edit_block_href = ""
        session_character_empty_state_title = ""
        session_character_empty_state_message = ""
        session_combat_relationship_available = False
        session_combat_relationship_surface_label = ""
        session_combat_relationship_action_label = ""
        session_combat_relationship_href = ""

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
            character_subpage = normalize_session_character_subpage(
                requested_subpage if requested_subpage is not None else request.args.get("page", ""),
                include_spellcasting=include_spellcasting_subpage,
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
            session_personal_edit_block_href = (
                build_session_character_read_view_url(
                    campaign.slug,
                    selected_character_slug,
                    "personal",
                )
                if can_view_full_character_sheet
                else ""
            )
            if session_character_editing_enabled:
                session_personal_edit_block_message = SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE
                if can_access_campaign_scope(campaign_slug, "combat"):
                    tracked_combatant = find_tracked_player_combatant_for_character(
                        campaign_slug,
                        selected_character_slug,
                        campaign=campaign,
                    )
                    if tracked_combatant is not None:
                        if can_manage_combat:
                            session_combat_relationship_available = True
                            session_combat_relationship_surface_label = "Encounter status"
                            session_combat_relationship_action_label = "Open encounter status"
                            session_combat_relationship_href = url_for(
                                "campaign_combat_status_view",
                                campaign_slug=campaign.slug,
                                combatant=tracked_combatant.id,
                            )
                        elif selected_character_slug in get_owned_character_slugs(campaign_slug):
                            session_combat_relationship_available = True
                            session_combat_relationship_surface_label = "Combat"
                            session_combat_relationship_action_label = "Open Combat"
                            session_combat_relationship_href = url_for(
                                "campaign_combat_view",
                                campaign_slug=campaign.slug,
                                combatant=tracked_combatant.id,
                            )
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
            "session_character_cards": session_character_cards,
            "session_character_access_summary": build_session_character_access_summary(
                campaign_slug,
                can_manage_session=can_manage_session,
                accessible_records=accessible_records,
            ),
            "session_character_permission_note": SESSION_CHARACTER_PERMISSION_NOTE,
            "session_character_permission_rules": SESSION_CHARACTER_PERMISSION_RULES,
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
            "session_character_active_edit_scope": (
                SESSION_CHARACTER_ACTIVE_EDIT_SCOPE if session_character_editing_enabled else ()
            ),
            "session_character_active_edit_summary": (
                SESSION_CHARACTER_ACTIVE_EDIT_SUMMARY if session_character_editing_enabled else ""
            ),
            "session_character_outside_edit_scope": (
                SESSION_CHARACTER_FULL_PAGE_ONLY_SCOPE if session_character_editing_enabled else ()
            ),
            "session_character_full_page_only_summary": (
                SESSION_CHARACTER_FULL_PAGE_ONLY_SUMMARY if session_character_editing_enabled else ""
            ),
            "session_personal_editing_enabled": session_personal_editing_enabled,
            "session_personal_edit_block_message": session_personal_edit_block_message,
            "session_personal_edit_block_href": session_personal_edit_block_href,
            "session_combat_relationship_available": session_combat_relationship_available,
            "session_combat_relationship_surface_label": session_combat_relationship_surface_label,
            "session_combat_relationship_action_label": session_combat_relationship_action_label,
            "session_combat_relationship_href": session_combat_relationship_href,
            "combat_and_session_combat_scope": COMBAT_AND_SESSION_COMBAT_SCOPE,
            "combat_and_session_combat_scope_summary": (
                COMBAT_AND_SESSION_COMBAT_SUMMARY if session_combat_relationship_available else ""
            ),
            "combat_and_session_session_scope": COMBAT_AND_SESSION_SESSION_SCOPE,
            "combat_and_session_session_scope_summary": (
                COMBAT_AND_SESSION_SESSION_SUMMARY if session_combat_relationship_available else ""
            ),
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
        return render_template("session_character.html", **context), status_code

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

    def build_session_character_sections(
        character_detail: dict[str, object],
        *,
        equipment_state_manager: dict[str, object] | None = None,
        include_spellcasting: bool = False,
    ) -> list[dict[str, object]]:
        spellcasting = dict(character_detail.get("spellcasting") or {})
        resources = [dict(item or {}) for item in list(character_detail.get("resources") or [])]
        feature_groups = [dict(group or {}) for group in list(character_detail.get("feature_groups") or [])]
        overview_stats = [dict(item or {}) for item in list(character_detail.get("overview_stats") or [])]
        defensive_rules = [dict(item or {}) for item in list(character_detail.get("defensive_rules") or [])]
        equipment_rows = [
            dict(item or {})
            for item in list((equipment_state_manager or {}).get("rows") or [])
        ]
        inventory_rows = [dict(item or {}) for item in list(character_detail.get("inventory") or [])]
        skills = [dict(item or {}) for item in list(character_detail.get("skills") or [])]
        reference_sections = [
            dict(item or {}) for item in list(character_detail.get("reference_sections") or [])
        ]
        spell_count = sum(
            len(list(section.get("spells") or []))
            for section in list(spellcasting.get("row_sections") or [])
            if isinstance(section, dict)
        )

        sections = [
            {
                "slug": "overview",
                "label": SESSION_CHARACTER_SECTION_LABELS["overview"],
                "count": len(overview_stats) + len(defensive_rules),
            },
        ]
        if include_spellcasting:
            sections.append(
                {
                    "slug": "spells",
                    "label": SESSION_CHARACTER_SECTION_LABELS["spells"],
                    "count": spell_count,
                }
            )
        sections.extend(
            [
                {
                    "slug": "resources",
                    "label": SESSION_CHARACTER_SECTION_LABELS["resources"],
                    "count": len(resources),
                },
                {
                    "slug": "features",
                    "label": SESSION_CHARACTER_SECTION_LABELS["features"],
                    "count": sum(
                        len(list(group.get("entries") or [])) for group in feature_groups
                    ),
                },
                {
                    "slug": "equipment",
                    "label": SESSION_CHARACTER_SECTION_LABELS["equipment"],
                    "count": len(equipment_rows),
                },
                {
                    "slug": "inventory",
                    "label": SESSION_CHARACTER_SECTION_LABELS["inventory"],
                    "count": len(inventory_rows),
                },
                {
                    "slug": "abilities_skills",
                    "label": SESSION_CHARACTER_SECTION_LABELS["abilities_skills"],
                    "count": len(skills),
                },
                {
                    "slug": "notes",
                    "label": SESSION_CHARACTER_SECTION_LABELS["notes"],
                    "count": int(bool(character_detail.get("player_notes_html")))
                    + len(reference_sections),
                },
                {
                    "slug": "personal",
                    "label": SESSION_CHARACTER_SECTION_LABELS["personal"],
                    "count": (
                        int(bool(character_detail.get("portrait")))
                        + int(bool(character_detail.get("physical_description_html")))
                        + int(bool(character_detail.get("personal_background_html")))
                    ),
                },
            ]
        )
        return sections

    def build_combat_character_workspace_sections(
        character_detail: dict[str, object],
        equipment_state_manager: dict[str, object],
    ) -> tuple[list[dict[str, object]], str]:
        action_features: list[dict[str, object]] = []
        bonus_action_features: list[dict[str, object]] = []
        reaction_features: list[dict[str, object]] = []
        feature_groups = [dict(group or {}) for group in list(character_detail.get("feature_groups") or [])]
        for group in feature_groups:
            group_title = str(group.get("title") or "Features").strip() or "Features"
            for feature in list(group.get("entries") or []):
                feature_payload = dict(feature or {})
                feature_payload["group_title"] = group_title
                activation_type = str(feature_payload.get("activation_type") or "").strip().lower()
                if activation_type == "action":
                    action_features.append(feature_payload)
                elif activation_type == "bonus_action":
                    bonus_action_features.append(feature_payload)
                elif activation_type == "reaction":
                    reaction_features.append(feature_payload)

        attack_reminders = [dict(item or {}) for item in list(character_detail.get("attack_reminders") or [])]
        defensive_rules = [dict(item or {}) for item in list(character_detail.get("defensive_rules") or [])]
        spellcasting = dict(character_detail.get("spellcasting") or {})
        resources = [dict(item or {}) for item in list(character_detail.get("resources") or [])]
        attacks = [dict(item or {}) for item in list(character_detail.get("attacks") or [])]
        hidden_attacks = []
        for item in list(character_detail.get("hidden_attacks") or []):
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                hidden_attacks.append(
                    {
                        "name": name,
                        "href": str(item.get("href") or "").strip(),
                    }
                )
                continue
            name = str(item).strip()
            if not name:
                continue
            hidden_attacks.append({"name": name, "href": ""})
        equipment_rows = [dict(item or {}) for item in list(equipment_state_manager.get("rows") or [])]
        inventory_rows = [dict(item or {}) for item in list(character_detail.get("inventory") or [])]
        equipment_item_refs = {
            str(item_ref).strip()
            for item_ref in list(equipment_state_manager.get("equipment_item_refs") or [])
            if str(item_ref).strip()
        }
        attunable_item_refs = {
            str(item_ref).strip()
            for item_ref in list(equipment_state_manager.get("attunable_item_refs") or [])
            if str(item_ref).strip()
        }
        for item in inventory_rows:
            item_ref = str(item.get("item_ref") or item.get("id") or "").strip()
            item["show_equipped_badge"] = bool(item_ref in equipment_item_refs and item.get("is_equipped"))
            item["show_attuned_badge"] = bool(item_ref in attunable_item_refs and item.get("is_attuned"))
        currency_rows = [dict(item or {}) for item in list(character_detail.get("currency") or [])]
        other_currency = [str(item).strip() for item in list(character_detail.get("other_currency") or []) if str(item).strip()]
        abilities = [dict(item or {}) for item in list(character_detail.get("abilities") or [])]
        skills = [dict(item or {}) for item in list(character_detail.get("skills") or [])]
        proficiency_groups = [dict(item or {}) for item in list(character_detail.get("proficiency_groups") or [])]

        spell_count = sum(
            len(list(section.get("spells") or []))
            for section in list(spellcasting.get("row_sections") or [])
            if isinstance(section, dict)
        )
        sections = [
            {
                "slug": "actions",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["actions"],
                "count": len(action_features),
                "has_content": bool(action_features),
                "features": action_features,
                "empty_message": "No action-specific features are recorded on this sheet yet.",
            },
            {
                "slug": "bonus_actions",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["bonus_actions"],
                "count": len(bonus_action_features),
                "has_content": bool(bonus_action_features),
                "features": bonus_action_features,
                "empty_message": "No bonus-action features are recorded on this sheet yet.",
            },
            {
                "slug": "reactions",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["reactions"],
                "count": len(reaction_features),
                "has_content": bool(reaction_features),
                "features": reaction_features,
                "empty_message": "No reaction features are recorded on this sheet yet.",
            },
            {
                "slug": "attacks",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["attacks"],
                "count": len(attacks),
                "has_content": bool(attacks or hidden_attacks or attack_reminders),
                "attacks": attacks,
                "hidden_attacks": hidden_attacks,
                "attack_reminders": attack_reminders,
                "empty_message": "No attacks are currently active on this sheet.",
            },
            {
                "slug": "spells",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["spells"],
                "count": spell_count,
                "has_content": bool(spellcasting),
                "spellcasting": spellcasting,
                "empty_message": "No spellcasting details are recorded on this sheet.",
            },
            {
                "slug": "resources",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["resources"],
                "count": len(resources),
                "has_content": bool(resources),
                "resources": resources,
                "empty_message": "No tracked limited-use resources are recorded on this sheet.",
            },
            {
                "slug": "features",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["features"],
                "count": sum(len(list(group.get("entries") or [])) for group in feature_groups),
                "has_content": bool(feature_groups or defensive_rules),
                "feature_groups": feature_groups,
                "defensive_rules": defensive_rules,
                "empty_message": "No feature details are recorded on this sheet yet.",
            },
            {
                "slug": "equipment",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["equipment"],
                "count": len(equipment_rows),
                "has_content": bool(equipment_rows),
                "equipment_state_manager": equipment_state_manager,
                "empty_message": "No equipment is listed on this sheet yet.",
            },
            {
                "slug": "inventory",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["inventory"],
                "count": len(inventory_rows),
                "has_content": bool(
                    inventory_rows
                    or any(int(item.get("amount") or 0) for item in currency_rows)
                    or other_currency
                ),
                "inventory": inventory_rows,
                "currency": currency_rows,
                "other_currency": other_currency,
                "empty_message": "No inventory or currency is listed on this sheet yet.",
            },
            {
                "slug": "abilities_skills",
                "label": COMBAT_CHARACTER_WORKSPACE_SECTION_LABELS["abilities_skills"],
                "count": len(skills),
                "has_content": bool(abilities or skills or proficiency_groups),
                "abilities": abilities,
                "skills": skills,
                "proficiency_groups": proficiency_groups,
                "empty_message": "No ability or skill details are recorded on this sheet yet.",
            },
        ]
        default_section = next((section["slug"] for section in sections if section["has_content"]), "actions")
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
    ) -> dict[str, object]:
        requested_combatant_id = (
            selected_combatant_id
            if selected_combatant_id is not None
            else parse_requested_combatant_id()
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
                combat_character_state_token = build_selected_combatant_state_token(
                    tracker_view,
                    selected_combatant,
                )
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
        combat_live_view_token = build_combat_live_view_token(
            campaign_slug,
            combat_subpage,
            selected_combatant_id=requested_combatant_id,
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
            "active_nav": "combat",
            "_combatant_records": combatants,
            "_combat_conditions_by_combatant": conditions_by_combatant,
            "_combat_character_records_by_slug": character_records_by_slug,
            "_selected_combatant_record": selected_combatant_record,
        }
        context.update(player_workspace_detail_context)
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
            }
        )
        context.update(source_context)
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

        custom_entry_form_visibility = "players"
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
        summary_template = (
            "_combat_character_snapshot.html"
            if context.get("show_player_combat_workspace")
            else "_combat_summary_card.html"
        )
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
            "summary_html": render_template(summary_template, **context),
            "tracker_html": render_template(tracker_template, **context),
            "context_html": render_template(sidebar_template, **context),
            "selected_combatant_id": context["selected_combatant_id"],
        }
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
            "tracker_html": render_template("_combat_dm_focus_card.html", **context),
            "controls_html": render_template("_combat_dm_controls.html", **context),
            "selected_combatant_id": context["selected_combatant_id"],
        }
        payload.update(
            build_combat_surface_urls(
                campaign_slug,
                combat_subpage="dm",
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
    ) -> dict[str, object]:
        context = build_campaign_combat_status_context(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
            sync_player_character_snapshots=sync_player_character_snapshots,
            strict_selected_combatant=False,
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
            if combat_return_view == "status":
                return jsonify(
                    build_campaign_combat_status_live_state(
                        campaign_slug,
                        include_flash=True,
                        mutation_succeeded=mutation_succeeded,
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
        if combat_return_view == "status":
            return redirect_to_campaign_combat_status(
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

    @app.get("/campaigns/<campaign_slug>/help")
    @campaign_scope_access_required("campaign")
    def campaign_help_view(campaign_slug: str):
        context = build_campaign_help_context(campaign_slug)
        return render_template("campaign_help.html", **context)

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

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
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
            if return_to_dm_content_systems:
                return render_template(
                    "dm_content.html",
                    **build_campaign_dm_content_page_context(campaign_slug, dm_content_subpage="systems"),
                ), 400
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

        if return_to_dm_content_systems:
            return redirect_to_campaign_dm_content(
                campaign_slug,
                subpage="systems",
                anchor="systems-source-enablement",
            )
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

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
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
            if return_to_dm_content_systems:
                return render_template(
                    "dm_content.html",
                    **build_campaign_dm_content_page_context(campaign_slug, dm_content_subpage="systems"),
                ), 400
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
        if return_to_dm_content_systems:
            return redirect_to_campaign_dm_content(
                campaign_slug,
                subpage="systems",
                anchor="systems-entry-overrides",
            )
        return redirect(url_for("campaign_systems_control_panel_view", campaign_slug=campaign_slug))

    def render_custom_systems_entry_management(
        campaign_slug: str,
        *,
        return_to_dm_content_systems: bool,
        edit_entry=None,
        form_data=None,
        status_code: int = 200,
    ):
        if return_to_dm_content_systems:
            return render_template(
                "dm_content.html",
                **build_campaign_dm_content_page_context(
                    campaign_slug,
                    dm_content_subpage="systems",
                    custom_systems_edit_entry=edit_entry,
                    custom_systems_entry_form_data=form_data,
                ),
            ), status_code
        return render_template(
            "campaign_systems_control_panel.html",
            **build_campaign_systems_control_context(
                campaign_slug,
                custom_systems_edit_entry=edit_entry,
                custom_systems_entry_form_data=form_data,
            ),
        ), status_code

    def redirect_after_custom_systems_entry(
        campaign_slug: str,
        *,
        return_to_dm_content_systems: bool,
        anchor: str = "systems-custom-entries",
    ):
        if return_to_dm_content_systems:
            return redirect_to_campaign_dm_content(
                campaign_slug,
                subpage="systems",
                anchor=anchor,
            )
        return redirect(
            url_for(
                "campaign_systems_control_panel_view",
                campaign_slug=campaign_slug,
                _anchor=anchor,
            )
        )

    def get_shared_systems_entry_for_edit_route(campaign_slug: str, entry_slug: str):
        systems_service = get_systems_service()
        entry = systems_service.get_entry_by_slug_for_campaign(campaign_slug, entry_slug)
        if entry is None:
            abort(404)
        source_state = systems_service.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None or systems_service.is_campaign_custom_entry(campaign_slug, entry):
            abort(404)
        return entry

    def render_shared_systems_entry_editor(
        campaign_slug: str,
        entry,
        *,
        form_data=None,
        status_code: int = 200,
    ):
        campaign = load_campaign_context(campaign_slug)
        systems_service = get_systems_service()
        source_state = systems_service.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None:
            abort(404)
        return render_template(
            "systems_shared_entry_edit.html",
            campaign=campaign,
            entry=entry,
            source_state=source_state,
            entry_type_label=SYSTEMS_ENTRY_TYPE_LABELS.get(
                entry.entry_type,
                entry.entry_type.replace("_", " ").title(),
            ),
            shared_systems_entry_form=build_shared_systems_entry_form(
                entry=entry,
                form_data=form_data,
            ),
            shared_systems_entry_mechanics_warning=(
                systems_service.build_shared_core_entry_mechanics_impact_warning(entry)
            ),
            active_nav="systems",
        ), status_code

    @app.get("/campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>/edit")
    @login_required
    def campaign_systems_control_panel_edit_shared_entry(campaign_slug: str, entry_slug: str):
        load_campaign_context(campaign_slug)
        if not can_edit_shared_systems_entries(campaign_slug):
            abort(403)
        entry = get_shared_systems_entry_for_edit_route(campaign_slug, entry_slug)
        return render_shared_systems_entry_editor(campaign_slug, entry)

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/shared-entries/<entry_slug>")
    @login_required
    def campaign_systems_control_panel_update_shared_entry(campaign_slug: str, entry_slug: str):
        load_campaign_context(campaign_slug)
        if not can_edit_shared_systems_entries(campaign_slug):
            abort(403)
        user = get_current_user()
        if user is None:
            abort(403)
        entry = get_shared_systems_entry_for_edit_route(campaign_slug, entry_slug)
        systems_service = get_systems_service()
        mechanics_warning = systems_service.build_shared_core_entry_mechanics_impact_warning(entry)
        if (
            mechanics_warning is not None
            and request.form.get("shared_entry_mechanics_impact_acknowledged") != "1"
        ):
            flash(
                "Review and acknowledge the mechanics impact warning before saving this shared/core Systems entry.",
                "error",
            )
            return render_shared_systems_entry_editor(
                campaign_slug,
                entry,
                form_data=request.form,
                status_code=400,
            )
        original_source_identity = build_shared_systems_entry_original_source_identity(entry)
        try:
            metadata = parse_shared_systems_entry_json_field(
                request.form.get("shared_entry_metadata_json", ""),
                field_label="Metadata JSON",
            )
            body = parse_shared_systems_entry_json_field(
                request.form.get("shared_entry_body_json", ""),
                field_label="Body JSON",
            )
            updated_entry = systems_service.update_shared_core_entry(
                campaign_slug,
                entry_slug,
                title=request.form.get("shared_entry_title", ""),
                source_page=request.form.get("shared_entry_source_page", ""),
                source_path=request.form.get("shared_entry_source_path", ""),
                search_text=request.form.get("shared_entry_search_text", ""),
                player_safe_default=request.form.get("shared_entry_player_safe_default") == "1",
                dm_heavy=request.form.get("shared_entry_dm_heavy") == "1",
                metadata=metadata,
                body=body,
                rendered_html=request.form.get("shared_entry_rendered_html", ""),
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return render_shared_systems_entry_editor(
                campaign_slug,
                entry,
                form_data=request.form,
                status_code=400,
            )

        edited_fields = list_shared_systems_entry_changed_fields(entry, updated_entry)
        audit_metadata = {
            "campaign_slug": campaign_slug,
            "library_slug": updated_entry.library_slug,
            "source_id": updated_entry.source_id,
            "entry_key": updated_entry.entry_key,
            "entry_slug": updated_entry.slug,
            "source": "campaign_systems_shared_entry_editor",
            "original_source_identity": original_source_identity,
            "edited_fields": edited_fields,
        }
        systems_service.store.record_shared_entry_edit_event(
            campaign_slug=campaign_slug,
            library_slug=updated_entry.library_slug,
            source_id=updated_entry.source_id,
            entry_key=updated_entry.entry_key,
            entry_slug=updated_entry.slug,
            original_source_identity=original_source_identity,
            edited_fields=edited_fields,
            actor_user_id=user.id,
            audit_event_type="campaign_systems_shared_entry_updated",
            audit_metadata=audit_metadata,
        )
        get_auth_store().write_audit_event(
            event_type="campaign_systems_shared_entry_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata=audit_metadata,
        )
        flash(f"Saved shared/core Systems entry {updated_entry.title}.", "success")
        return redirect(
            url_for(
                "campaign_systems_entry_detail",
                campaign_slug=campaign_slug,
                entry_slug=updated_entry.slug,
                _anchor="systems-entry-management",
            )
        )

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/custom-entries")
    @login_required
    def campaign_systems_control_panel_create_custom_entry(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
        try:
            entry = get_systems_service().create_custom_campaign_entry(
                campaign_slug,
                title=request.form.get("custom_entry_title", ""),
                entry_type=request.form.get("custom_entry_type", ""),
                slug_leaf=request.form.get("custom_entry_slug", ""),
                provenance=request.form.get("custom_entry_provenance", ""),
                visibility=request.form.get("custom_entry_visibility", ""),
                search_metadata=request.form.get("custom_entry_search_metadata", ""),
                body_markdown=request.form.get("custom_entry_body_markdown", ""),
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return render_custom_systems_entry_management(
                campaign_slug,
                return_to_dm_content_systems=return_to_dm_content_systems,
                form_data=request.form,
                status_code=400,
            )

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_created",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "source": "campaign_systems_control_panel",
            },
        )
        flash(f"Custom Systems entry {entry.title} saved.", "success")
        return redirect_after_custom_systems_entry(
            campaign_slug,
            return_to_dm_content_systems=return_to_dm_content_systems,
            anchor=f"systems-custom-entry-{custom_systems_entry_dom_id(entry)}",
        )

    @app.get("/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/edit")
    @login_required
    def campaign_systems_control_panel_edit_custom_entry(campaign_slug: str, entry_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        entry = get_systems_service().get_custom_campaign_entry_by_slug(campaign_slug, entry_slug)
        if entry is None:
            abort(404)
        return render_custom_systems_entry_management(
            campaign_slug,
            return_to_dm_content_systems=request.args.get("return_to") == "dm-content-systems",
            edit_entry=entry,
        )

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>")
    @login_required
    def campaign_systems_control_panel_update_custom_entry(campaign_slug: str, entry_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        systems_service = get_systems_service()
        edit_entry = systems_service.get_custom_campaign_entry_by_slug(campaign_slug, entry_slug)
        if edit_entry is None:
            abort(404)

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
        try:
            entry = systems_service.update_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                title=request.form.get("custom_entry_title", ""),
                entry_type=request.form.get("custom_entry_type", ""),
                provenance=request.form.get("custom_entry_provenance", ""),
                visibility=request.form.get("custom_entry_visibility", ""),
                search_metadata=request.form.get("custom_entry_search_metadata", ""),
                body_markdown=request.form.get("custom_entry_body_markdown", ""),
                actor_user_id=user.id,
                can_set_private=bool(user.is_admin),
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return render_custom_systems_entry_management(
                campaign_slug,
                return_to_dm_content_systems=return_to_dm_content_systems,
                edit_entry=edit_entry,
                form_data=request.form,
                status_code=400,
            )

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "entry_type": entry.entry_type,
                "source": "campaign_systems_control_panel",
            },
        )
        flash(f"Custom Systems entry {entry.title} updated.", "success")
        return redirect_after_custom_systems_entry(
            campaign_slug,
            return_to_dm_content_systems=return_to_dm_content_systems,
            anchor=f"systems-custom-entry-{custom_systems_entry_dom_id(entry)}",
        )

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/archive")
    @login_required
    def campaign_systems_control_panel_archive_custom_entry(campaign_slug: str, entry_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
        try:
            entry = get_systems_service().archive_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                actor_user_id=user.id,
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return redirect_after_custom_systems_entry(
                campaign_slug,
                return_to_dm_content_systems=return_to_dm_content_systems,
            )

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_archived",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "source": "campaign_systems_control_panel",
            },
        )
        flash(f"Archived custom Systems entry {entry.title}.", "success")
        return redirect_after_custom_systems_entry(
            campaign_slug,
            return_to_dm_content_systems=return_to_dm_content_systems,
            anchor=f"systems-custom-entry-{custom_systems_entry_dom_id(entry)}",
        )

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/custom-entries/<entry_slug>/restore")
    @login_required
    def campaign_systems_control_panel_restore_custom_entry(campaign_slug: str, entry_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"
        try:
            entry = get_systems_service().restore_custom_campaign_entry(
                campaign_slug,
                entry_slug,
                actor_user_id=user.id,
            )
        except SystemsPolicyValidationError as exc:
            flash(str(exc), "error")
            return redirect_after_custom_systems_entry(
                campaign_slug,
                return_to_dm_content_systems=return_to_dm_content_systems,
            )

        get_auth_store().write_audit_event(
            event_type="campaign_systems_custom_entry_restored",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "entry_key": entry.entry_key,
                "entry_slug": entry.slug,
                "source": "campaign_systems_control_panel",
            },
        )
        flash(f"Restored custom Systems entry {entry.title}.", "success")
        return redirect_after_custom_systems_entry(
            campaign_slug,
            return_to_dm_content_systems=return_to_dm_content_systems,
            anchor=f"systems-custom-entry-{custom_systems_entry_dom_id(entry)}",
        )

    @app.post("/campaigns/<campaign_slug>/systems/control-panel/imports/dnd5e")
    @login_required
    def campaign_systems_control_panel_import_dnd5e(campaign_slug: str):
        load_campaign_context(campaign_slug)
        if not can_manage_campaign_systems(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None or not user.is_admin:
            abort(403)

        return_to_dm_content_systems = request.form.get("return_to") == "dm-content-systems"

        def render_import_error(message: str, *, status_code: int = 400):
            flash(message, "error")
            if return_to_dm_content_systems:
                return render_template(
                    "dm_content.html",
                    **build_campaign_dm_content_page_context(
                        campaign_slug,
                        dm_content_subpage="systems",
                        systems_import_form_data=request.form,
                    ),
                ), status_code
            return render_template(
                "campaign_systems_control_panel.html",
                **build_campaign_systems_control_context(
                    campaign_slug,
                    systems_import_form_data=request.form,
                ),
            ), status_code

        systems_service = get_systems_service()
        library_slug = systems_service.get_campaign_library_slug(campaign_slug)
        if not supports_dnd5e_systems_import(library_slug):
            return render_import_error("Browser source import is currently only available for DND-5E Systems libraries.")

        source_ids: list[str] = []
        seen_source_ids: set[str] = set()
        for raw_source_id in request.form.getlist("source_ids"):
            source_id = str(raw_source_id or "").strip().upper()
            if not source_id or source_id in seen_source_ids:
                continue
            source_ids.append(source_id)
            seen_source_ids.add(source_id)
        if not source_ids:
            return render_import_error("Choose at least one DND-5E source to import.")

        supported_browser_sources = {
            state.source.source_id
            for state in systems_service.list_campaign_source_states(campaign_slug)
            if state.source.source_id != "RULES" and state.source.license_class != "custom_campaign"
        }
        unsupported_source_ids = sorted(set(source_ids) - supported_browser_sources)
        if unsupported_source_ids:
            return render_import_error("Unsupported source IDs: " + ", ".join(unsupported_source_ids) + ".")

        selected_entry_types: list[str] = []
        seen_entry_types: set[str] = set()
        supported_entry_types = set(SUPPORTED_ENTRY_TYPES)
        for raw_entry_type in request.form.getlist("entry_types"):
            entry_type = str(raw_entry_type or "").strip().lower()
            if not entry_type or entry_type in seen_entry_types:
                continue
            selected_entry_types.append(entry_type)
            seen_entry_types.add(entry_type)
        invalid_entry_types = sorted(set(selected_entry_types) - supported_entry_types)
        if invalid_entry_types:
            return render_import_error("Unsupported entry types: " + ", ".join(invalid_entry_types) + ".")

        upload = request.files.get("systems_import_archive")
        archive_filename = str(getattr(upload, "filename", "") or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        if upload is None or not archive_filename:
            return render_import_error("Choose a ZIP archive to import.")
        if not archive_filename.lower().endswith(".zip"):
            return render_import_error("Systems source imports must be uploaded as a .zip archive.")

        archive_bytes = upload.read()
        if not archive_bytes:
            return render_import_error("Choose a non-empty ZIP archive to import.")

        import_version = request.form.get("import_version", "").strip() or Path(archive_filename).stem
        source_path_label = f"browser-upload:{archive_filename}"
        try:
            with extracted_systems_archive(archive_bytes) as data_root:
                importer = Dnd5eSystemsImporter(
                    store=systems_service.store,
                    systems_service=systems_service,
                    data_root=data_root,
                )
                results = importer.import_sources(
                    source_ids,
                    entry_types=selected_entry_types or None,
                    started_by_user_id=user.id,
                    import_version=import_version,
                    source_path_label=source_path_label,
                )
        except (FileNotFoundError, SystemsIngestError, ValueError) as exc:
            return render_import_error(str(exc))

        get_auth_store().write_audit_event(
            event_type="systems_dnd5e_source_imported",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "library_slug": library_slug,
                "source_ids": source_ids,
                "entry_types": selected_entry_types or ["all"],
                "import_run_ids": [result.import_run_id for result in results],
                "archive_filename": archive_filename,
                "source": "campaign_systems_control_panel",
            },
        )
        result_summary = ", ".join(f"{result.source_id} ({result.imported_count} entries)" for result in results)
        flash(f"Imported DND-5E Systems sources: {result_summary}.", "success")
        if return_to_dm_content_systems:
            return redirect_to_campaign_dm_content(
                campaign_slug,
                subpage="systems",
                anchor="systems-import-history",
            )
        return redirect(
            url_for(
                "campaign_systems_control_panel_view",
                campaign_slug=campaign_slug,
                _anchor="systems-import-history",
            )
        )

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

    @app.get("/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/edit")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_edit_player_wiki_page(campaign_slug: str, page_ref: str):
        if not can_manage_campaign_content(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        try:
            record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError):
            abort(404)
        if record is None:
            abort(404)

        context = build_campaign_dm_content_page_context(
            campaign_slug,
            dm_content_subpage="player-wiki",
            player_wiki_edit_record=record,
        )
        return render_template("dm_content.html", **context)

    @app.get("/campaigns/<campaign_slug>/dm-content/player-wiki/session-articles/<int:article_id>/new")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_new_player_wiki_page_from_session_article(campaign_slug: str, article_id: int):
        if not can_manage_campaign_content(campaign_slug) or not can_manage_campaign_session(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        session_service = get_campaign_session_service()
        article = session_service.get_article(campaign_slug, article_id)
        if article is None:
            abort(404)

        existing_page = find_published_page_for_session_article(campaign, article_id)
        if existing_page is not None:
            flash("This session article already has a wiki page. Edit the published page here.", "info")
            return redirect(
                url_for(
                    "campaign_dm_content_edit_player_wiki_page",
                    campaign_slug=campaign_slug,
                    page_ref=existing_page.route_slug,
                    _anchor="dm-content-player-wiki-editor",
                )
            )

        article_image = session_service.get_article_image(campaign_slug, article_id)
        context = build_campaign_dm_content_page_context(
            campaign_slug,
            dm_content_subpage="player-wiki",
            player_wiki_form_data=build_dm_player_wiki_session_article_form_data(
                campaign,
                article,
                article_image=article_image,
            ),
        )
        return render_template("dm_content.html", **context)

    @app.post("/campaigns/<campaign_slug>/dm-content/player-wiki/pages")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_create_player_wiki_page(campaign_slug: str):
        if not can_manage_campaign_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        try:
            page_ref, metadata, body_markdown = normalize_dm_player_wiki_form(
                campaign,
                form_data=request.form,
            )
            source_session_article_id = normalize_dm_player_wiki_source_session_article_id(
                request.form.get("source_session_article_id")
            )
            source_session_article_image = None
            if source_session_article_id is not None:
                session_service = get_campaign_session_service()
                session_article = session_service.get_article(campaign_slug, source_session_article_id)
                if session_article is None:
                    raise ValueError("The source session article could not be found.")
                existing_source_page = find_published_page_for_session_article(campaign, source_session_article_id)
                if existing_source_page is not None:
                    raise ValueError("This session article already has a wiki page. Edit that page instead.")
                metadata["source_ref"] = build_session_article_source_ref(campaign.slug, source_session_article_id)
                source_session_article_image = session_service.get_article_image(
                    campaign_slug,
                    source_session_article_id,
                )
            existing_record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
            if existing_record is not None:
                raise ValueError("That page slug is already in use. Choose a different slug.")
            uploaded_image_asset_ref = apply_dm_player_wiki_image_upload(campaign, page_ref, metadata)
            copied_session_article_image_asset_ref = ""
            if not uploaded_image_asset_ref:
                copied_session_article_image_asset_ref = apply_dm_player_wiki_session_article_image(
                    campaign,
                    page_ref,
                    metadata,
                    source_session_article_image,
                )
            record = write_campaign_page_file(
                campaign,
                page_ref,
                metadata=metadata,
                body_markdown=body_markdown,
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError) as exc:
            flash(str(exc), "error")
            context = build_campaign_dm_content_page_context(
                campaign_slug,
                dm_content_subpage="player-wiki",
                player_wiki_form_data=request.form,
            )
            return render_template("dm_content.html", **context), 400

        repository_store.refresh()
        get_auth_store().write_audit_event(
            event_type="campaign_wiki_page_created",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "page_ref": record.page_ref,
                "route_slug": record.page.route_slug,
                "source": "dm_content_player_wiki",
                "uploaded_image_asset_ref": uploaded_image_asset_ref,
                "copied_session_article_image_asset_ref": copied_session_article_image_asset_ref,
                "source_session_article_id": source_session_article_id,
            },
        )
        flash(f"Created wiki page {record.page.title}.", "success")
        return redirect(
            url_for(
                "campaign_dm_content_edit_player_wiki_page",
                campaign_slug=campaign_slug,
                page_ref=record.page_ref,
                _anchor="dm-content-player-wiki-editor",
            )
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_update_player_wiki_page(campaign_slug: str, page_ref: str):
        if not can_manage_campaign_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        try:
            existing_record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError):
            abort(404)
        if existing_record is None:
            abort(404)

        try:
            normalized_page_ref, metadata, body_markdown = normalize_dm_player_wiki_form(
                campaign,
                form_data=request.form,
                existing_record=existing_record,
            )
            uploaded_image_asset_ref = apply_dm_player_wiki_image_upload(
                campaign,
                normalized_page_ref,
                metadata,
            )
            record = write_campaign_page_file(
                campaign,
                normalized_page_ref,
                metadata=metadata,
                body_markdown=body_markdown,
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError) as exc:
            flash(str(exc), "error")
            context = build_campaign_dm_content_page_context(
                campaign_slug,
                dm_content_subpage="player-wiki",
                player_wiki_edit_record=existing_record,
                player_wiki_form_data=request.form,
            )
            return render_template("dm_content.html", **context), 400

        repository_store.refresh()
        get_auth_store().write_audit_event(
            event_type="campaign_wiki_page_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "page_ref": record.page_ref,
                "route_slug": record.page.route_slug,
                "source": "dm_content_player_wiki",
                "uploaded_image_asset_ref": uploaded_image_asset_ref,
            },
        )
        flash(f"Updated wiki page {record.page.title}.", "success")
        return redirect(
            url_for(
                "campaign_dm_content_edit_player_wiki_page",
                campaign_slug=campaign_slug,
                page_ref=record.page_ref,
                _anchor="dm-content-player-wiki-editor",
            )
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/unpublish")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_unpublish_player_wiki_page(campaign_slug: str, page_ref: str):
        if not can_manage_campaign_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        try:
            existing_record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError):
            abort(404)
        if existing_record is None:
            abort(404)

        metadata = dict(existing_record.metadata or {})
        metadata["published"] = False
        record = write_campaign_page_file(
            campaign,
            existing_record.page_ref,
            metadata=metadata,
            body_markdown=existing_record.body_markdown,
            page_store=get_campaign_page_store(),
        )
        repository_store.refresh()
        get_auth_store().write_audit_event(
            event_type="campaign_wiki_page_unpublished",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "page_ref": record.page_ref,
                "route_slug": record.page.route_slug,
                "source": "dm_content_player_wiki",
            },
        )
        flash(f"Unpublished wiki page {record.page.title}.", "success")
        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="player-wiki",
            anchor=f"wiki-page-{build_dm_player_wiki_page_summary(campaign, record)['dom_id']}",
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/player-wiki/pages/<path:page_ref>/delete")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_delete_player_wiki_page(campaign_slug: str, page_ref: str):
        if not can_manage_campaign_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        try:
            existing_record = get_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except (CampaignContentError, ValueError):
            abort(404)
        if existing_record is None:
            abort(404)

        if request.form.get("confirm_delete") != "1":
            flash("Confirm hard delete before removing a wiki page file.", "error")
            return redirect(
                url_for(
                    "campaign_dm_content_edit_player_wiki_page",
                    campaign_slug=campaign_slug,
                    page_ref=page_ref,
                    _anchor="dm-content-player-wiki-editor",
                )
            )

        player_wiki_records = list_campaign_page_files(
            campaign,
            page_store=get_campaign_page_store(),
        )
        removal_safety = build_dm_player_wiki_removal_safety_index(
            campaign_slug,
            campaign,
            player_wiki_records,
            session_articles=get_campaign_session_service().list_articles(campaign_slug),
            character_records=get_character_repository().list_characters(campaign_slug),
        ).get(existing_record.page_ref, {})
        hard_delete_blockers = list(removal_safety.get("hard_delete_blockers", []) or [])
        if hard_delete_blockers:
            flash(
                "Hard delete blocked. Unpublish/archive the page or remove: "
                + " ".join(hard_delete_blockers),
                "error",
            )
            return redirect_to_campaign_dm_content(
                campaign_slug,
                subpage="player-wiki",
                anchor=f"wiki-page-{build_dm_player_wiki_page_summary(campaign, existing_record)['dom_id']}",
            )

        try:
            deleted = delete_campaign_page_file(
                campaign,
                page_ref,
                page_store=get_campaign_page_store(),
            )
        except CampaignContentError as exc:
            flash(str(exc), "error")
            return redirect_to_campaign_dm_content(campaign_slug, subpage="player-wiki")
        if deleted is None:
            abort(404)

        repository_store.refresh()
        get_auth_store().write_audit_event(
            event_type="campaign_wiki_page_deleted",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "page_ref": deleted.page_ref,
                "route_slug": deleted.page.route_slug,
                "source": "dm_content_player_wiki",
            },
        )
        flash(f"Deleted wiki page {deleted.page.title}.", "success")
        return redirect_to_campaign_dm_content(campaign_slug, subpage="player-wiki")

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

    @app.post("/campaigns/<campaign_slug>/dm-content/statblocks")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_upload_statblock(campaign_slug: str):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        campaign = load_campaign_context(campaign_slug)
        if not supports_dnd5e_statblock_upload(campaign.system):
            flash(
                f"Statblock upload is only implemented for {DND_5E_SYSTEM_CODE} right now.",
                "error",
            )
            return redirect_to_campaign_dm_content(
                campaign_slug,
                subpage="statblocks",
                anchor="dm-content-statblocks",
            )

        user = get_current_user()
        if user is None:
            abort(403)

        markdown_file = request.files.get("statblock_file")
        filename = (markdown_file.filename or "").strip() if markdown_file is not None else ""
        data_blob = markdown_file.read() if markdown_file is not None else b""
        try:
            statblock = get_campaign_dm_content_service().create_statblock(
                campaign_slug,
                filename=filename,
                data_blob=data_blob,
                subsection=request.form.get("subsection", ""),
                created_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
        else:
            parser_feedback = build_statblock_parser_feedback(statblock)
            flash(f"Statblock saved to DM Content. {parser_feedback['summary']}", "success")

        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="statblocks",
            anchor="dm-content-statblocks",
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/statblocks/<int:statblock_id>")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_update_statblock(campaign_slug: str, statblock_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            statblock = get_campaign_dm_content_service().update_statblock(
                campaign_slug,
                statblock_id,
                body_markdown=request.form.get("body_markdown", ""),
                subsection=request.form.get("subsection", ""),
                updated_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
            context = build_campaign_dm_content_page_context(
                campaign_slug,
                dm_content_subpage="statblocks",
                dm_statblock_form_overrides={
                    statblock_id: {
                        "subsection": request.form.get("subsection", ""),
                        "body_markdown": request.form.get("body_markdown", ""),
                    }
                },
            )
            return render_template("dm_content.html", **context), 400

        parser_feedback = build_statblock_parser_feedback(statblock)
        get_auth_store().write_audit_event(
            event_type="campaign_dm_statblock_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "statblock_id": statblock.id,
                "title": statblock.title,
                "subsection": statblock.subsection,
                "source": "dm_content_statblocks",
                "parsed": {
                    "armor_class": statblock.armor_class,
                    "max_hp": statblock.max_hp,
                    "movement_total": statblock.movement_total,
                    "initiative_bonus": statblock.initiative_bonus,
                },
            },
        )
        flash(f"Statblock {statblock.title} updated. {parser_feedback['summary']}", "success")
        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="statblocks",
            anchor=f"dm-statblock-{statblock.id}",
        )

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

        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="statblocks",
            anchor="dm-content-statblocks",
        )

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

        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="conditions",
            anchor="dm-content-conditions",
        )

    @app.post("/campaigns/<campaign_slug>/dm-content/conditions/<int:condition_definition_id>")
    @campaign_scope_access_required("dm_content")
    def campaign_dm_content_update_condition_definition(campaign_slug: str, condition_definition_id: int):
        if not can_manage_campaign_dm_content(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        try:
            condition_definition = get_campaign_dm_content_service().update_condition_definition(
                campaign_slug,
                condition_definition_id,
                name=request.form.get("name", ""),
                description_markdown=request.form.get("description_markdown", ""),
                updated_by_user_id=user.id,
            )
        except CampaignDMContentValidationError as exc:
            flash(str(exc), "error")
            context = build_campaign_dm_content_page_context(
                campaign_slug,
                dm_content_subpage="conditions",
                dm_condition_form_overrides={
                    condition_definition_id: {
                        "name": request.form.get("name", ""),
                        "description_markdown": request.form.get("description_markdown", ""),
                    }
                },
            )
            return render_template("dm_content.html", **context), 400

        get_auth_store().write_audit_event(
            event_type="campaign_dm_condition_updated",
            actor_user_id=user.id,
            campaign_slug=campaign_slug,
            metadata={
                "condition_definition_id": condition_definition.id,
                "name": condition_definition.name,
                "source": "dm_content_conditions",
            },
        )
        flash(f"Custom condition {condition_definition.name} updated.", "success")
        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="conditions",
            anchor=f"dm-condition-{condition_definition.id}",
        )

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

        return redirect_to_campaign_dm_content(
            campaign_slug,
            subpage="conditions",
            anchor="dm-content-conditions",
        )

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
        selected_combatant_id = parse_requested_combatant_id()
        state_check_started_at = time.perf_counter()
        live_metadata = build_combat_live_metadata(
            campaign_slug,
            "status",
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
                view_name="combat-status",
                changed=False,
                live_revision=int(live_metadata["live_revision"] or 0),
                state_check_ms=state_check_ms,
                render_ms=0.0,
            )

        render_started_at = time.perf_counter()
        payload = build_campaign_combat_status_live_state(
            campaign_slug,
            selected_combatant_id=selected_combatant_id,
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
            expected_combatant_revision = parse_expected_combatant_revision()
            get_campaign_combat_service().update_turn_value(
                campaign_slug,
                combatant_id,
                expected_revision=expected_combatant_revision,
                turn_value=request.form.get("turn_value"),
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            flash("This combatant changed in another combat view. Refresh and try again.", "error")
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
            expected_combatant_revision = parse_expected_combatant_revision()
            get_campaign_combat_service().update_player_detail_visibility(
                campaign_slug,
                combatant_id,
                expected_revision=expected_combatant_revision,
                player_detail_visible=request.form.get("player_detail_visible") == "1",
                updated_by_user_id=user.id,
            )
        except CampaignCombatRevisionConflictError:
            flash("This combatant changed in another combat view. Refresh and try again.", "error")
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

    @app.get("/campaigns/<campaign_slug>/session/character")
    @campaign_scope_access_required("session")
    def campaign_session_character_view(campaign_slug: str):
        context = build_campaign_session_character_page_context(campaign_slug)
        return render_template("session_character.html", **context)

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

        article_mode = normalize_session_article_form_mode(request.form.get("article_mode", "manual"))
        source_kind = ""
        mutation_succeeded = False
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

    @app.post("/campaigns/<campaign_slug>/session/articles/<int:article_id>")
    @campaign_scope_access_required("session")
    def campaign_session_update_article(campaign_slug: str, article_id: int):
        if not can_manage_campaign_session(campaign_slug):
            abort(403)

        user = get_current_user()
        if user is None:
            abort(403)

        mutation_succeeded = False
        try:
            update_session_article_from_request(
                campaign_slug,
                article_id,
                updated_by_user_id=user.id,
            )
        except CampaignSessionValidationError as exc:
            flash(str(exc), "error")
        else:
            flash("Session article updated.", "success")
            mutation_succeeded = True

        return respond_to_campaign_session_mutation(
            campaign_slug,
            mutation_succeeded=mutation_succeeded,
            anchor="session-staged-articles",
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
        native_character_tools_supported = campaign_supports_native_character_create(campaign)

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
        if not campaign_supports_native_character_create(campaign):
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

    @app.route("/campaigns/<campaign_slug>/characters/<character_slug>/level-up", methods=["GET", "POST"])
    @campaign_scope_access_required("characters")
    def character_level_up_view(campaign_slug: str, character_slug: str):
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

    @app.get("/campaigns/<campaign_slug>/characters/<character_slug>")
    @campaign_scope_access_required("characters")
    def character_read_view(campaign_slug: str, character_slug: str):
        return render_character_page(campaign_slug, character_slug)

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
                weapon_wield_mode = _normalize_weapon_wield_mode_value(request.form.get("weapon_wield_mode"))
                allowed_modes = [
                    _normalize_weapon_wield_mode_value(value)
                    for value in list(target_support.get("weapon_wield_modes") or [])
                    if _normalize_weapon_wield_mode_value(value)
                ]
                allowed_mode_set = {
                    _normalize_weapon_wield_mode_value(value)
                    for value in list(target_support.get("weapon_wield_modes") or [])
                    if _normalize_weapon_wield_mode_value(value)
                }
                if weapon_wield_mode and weapon_wield_mode not in allowed_mode_set:
                    raise CharacterEditValidationError("Choose a valid wielding mode for that weapon.")
                if not weapon_wield_mode and bool(request.form.get("is_equipped")) and allowed_modes:
                    weapon_wield_mode = allowed_modes[0]
                is_equipped = bool(weapon_wield_mode)
            else:
                is_equipped = bool(request.form.get("is_equipped"))
            requested_attunement = bool(request.form.get("is_attuned"))
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
                systems_service=get_systems_service(),
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
            flash(SESSION_CHARACTER_PERSONAL_EDIT_BLOCK_MESSAGE, "error")
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
