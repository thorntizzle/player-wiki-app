from __future__ import annotations

from html import escape
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from flask import g, has_request_context

from .auth_store import isoformat, utcnow
from .character_campaign_progression import build_campaign_page_progression_entries
from .campaign_visibility import (
    VISIBILITY_DM,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    is_valid_visibility,
    most_private_visibility,
    normalize_visibility_choice,
)
from .dnd5e_rules_reference import (
    DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY,
    DND5E_RULES_REFERENCE_SOURCE_ID,
    DND5E_RULES_REFERENCE_SOURCE_TITLE,
    DND5E_RULES_REFERENCE_VERSION,
    build_dnd5e_rules_reference_entries,
)
from .repository import normalize_lookup, slugify
from .repository_store import RepositoryStore
from .systems_models import (
    CampaignSystemsPolicyRecord,
    SystemsEntryRecord,
    SystemsLibraryRecord,
    SystemsSourceRecord,
)
from .systems_store import SystemsStore

LICENSE_CLASS_LABELS = {
    "app_reference": "App-authored reference",
    "proprietary_private": "Proprietary - private campaign use",
    "srd_cc": "SRD - Creative Commons",
    "open_license": "Open license",
    "custom_campaign": "Custom campaign",
}

INLINE_TAG_PATTERN = re.compile(r"\{@([^{}]+)\}")

ATTACK_TAG_LABELS = {
    "mw": "Melee Weapon Attack:",
    "rw": "Ranged Weapon Attack:",
    "mw,rw": "Melee or Ranged Weapon Attack:",
    "ms": "Melee Spell Attack:",
    "rs": "Ranged Spell Attack:",
    "ms,rs": "Melee or Ranged Spell Attack:",
}

ARMOR_ITEM_TYPE_CODES = {"LA", "MA", "HA", "S"}
WEAPON_ITEM_TYPE_CODES = {"M", "R"}
PASSIVE_CHECK_SKILL_KEYS = {"insight", "investigation", "perception"}
RULES_REFERENCE_ENTRY_TYPES = ("book", "rule")
RULES_REFERENCE_SEARCH_SCOPE_GLOBAL = "global"
RULES_REFERENCE_SEARCH_SCOPE_SOURCE_ONLY = "source_only"
PHB_BOOK_SECTION_RULE_KEY_MAP = {
    # Only link section anchors whose rule identity already exists as a stable RULES entry.
    "2-choose-a-class--hit-points-and-hit-dice": ("hit-points-and-hit-dice",),
    "2-choose-a-class--proficiency-bonus": ("proficiency-bonus",),
    "5-choose-equipment--armor-class": ("armor-class",),
    "ability-scores-and-modifiers": ("ability-scores-and-ability-modifiers",),
    "proficiency-bonus": ("proficiency-bonus",),
    "ability-checks--skills": ("skill-bonuses-and-proficiency",),
    "ability-checks--passive-checks": ("passive-checks",),
    "saving-throws": ("saving-throw-bonuses",),
    "movement--resting": ("hit-points-and-hit-dice",),
    "the-order-of-combat--initiative": ("initiative",),
    "making-an-attack": ("attack-rolls-and-attack-bonus",),
    "making-an-attack--attack-rolls": ("attack-rolls-and-attack-bonus",),
    "damage-and-healing--hit-points": ("hit-points-and-hit-dice",),
    "damage-and-healing--damage-rolls": ("damage-rolls",),
    "damage-and-healing--dropping-to-0-hit-points": ("hit-points-and-hit-dice",),
    "damage-and-healing--temporary-hit-points": ("hit-points-and-hit-dice",),
    "casting-a-spell--saving-throws": ("spell-attacks-and-save-dcs",),
    "casting-a-spell--attack-rolls": ("spell-attacks-and-save-dcs",),
}
BOOK_SECTION_ENTITY_TAG_ENTRY_TYPES = {
    "action": "action",
    "background": "background",
    "class": "class",
    "condition": "condition",
    "creature": "monster",
    "disease": "disease",
    "feat": "feat",
    "status": "status",
    "skill": "skill",
    "sense": "sense",
    "spell": "spell",
    "item": "item",
    "monster": "monster",
    "optionalfeature": "optionalfeature",
    "race": "race",
    "subclass": "subclass",
    "variantrule": "variantrule",
}
BOOK_SECTION_ENTITY_TYPE_ORDER = (
    "condition",
    "disease",
    "status",
    "action",
    "skill",
    "sense",
    "spell",
    "variantrule",
    "feat",
    "item",
    "background",
    "race",
    "class",
    "subclass",
    "monster",
    "optionalfeature",
)
BOOK_SECTION_ENTITY_GROUP_LABELS = {
    "condition": "Conditions",
    "disease": "Diseases",
    "status": "Statuses",
    "action": "Actions",
    "skill": "Skills",
    "sense": "Senses",
    "spell": "Spells",
    "variantrule": "Variant Rules",
    "feat": "Feats",
    "item": "Equipment",
    "background": "Backgrounds",
    "race": "Races",
    "class": "Classes",
    "subclass": "Subclasses",
    "monster": "Monsters",
    "optionalfeature": "Optional Features",
}
BOOK_SECTION_ENTITY_SOURCE_FALLBACKS = {
    "MM": {
        "action": ("PHB",),
        "condition": ("PHB",),
        "sense": ("PHB",),
        "skill": ("PHB",),
        "status": ("PHB",),
    },
}


def _normalized_nonempty_tuple(*values: str) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        normalized_value = normalize_lookup(value)
        if normalized_value:
            normalized_values.append(normalized_value)
    return tuple(normalized_values)


VGM_MONSTER_LORE_WRAPPER_MONSTER_MATCHERS = {
    normalize_lookup("Beholders: Bad Dreams Come True"): {
        "group_keys": _normalized_nonempty_tuple("Beholders"),
        "type_keys": (),
        "tag_keys": (),
        "title_keys": _normalized_nonempty_tuple(
            "Beholder",
            "Death Tyrant",
            "Death Kiss",
            "Gauth",
            "Gazer",
            "Spectator",
        ),
        "title_prefix_keys": (),
        "title_suffix_keys": (),
    },
    normalize_lookup("Giants: World Shakers"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple(
            "cloud giant",
            "fire giant",
            "frost giant",
            "hill giant",
            "stone giant",
            "storm giant",
        ),
        "title_keys": _normalized_nonempty_tuple(
            "Cloud Giant",
            "Fire Giant",
            "Frost Giant",
            "Hill Giant",
            "Stone Giant",
            "Storm Giant",
            "Mouth of Grolantor",
        ),
        "title_prefix_keys": _normalized_nonempty_tuple(
            "Cloud Giant",
            "Fire Giant",
            "Frost Giant",
            "Hill Giant",
            "Stone Giant",
            "Storm Giant",
        ),
        "title_suffix_keys": (),
    },
    normalize_lookup("Gnolls: The Insatiable Hunger"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("gnoll"),
        "title_keys": _normalized_nonempty_tuple("Flind"),
        "title_prefix_keys": _normalized_nonempty_tuple("Gnoll"),
        "title_suffix_keys": (),
    },
    normalize_lookup("Goblinoids: The Conquering Host"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("goblinoid"),
        "title_keys": (),
        "title_prefix_keys": (),
        "title_suffix_keys": (),
    },
    normalize_lookup("Hags: Dark Sisterhood"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": (),
        "title_keys": (),
        "title_prefix_keys": (),
        "title_suffix_keys": _normalized_nonempty_tuple("Hag"),
    },
    normalize_lookup("Kobolds: Little Dragons"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("kobold"),
        "title_keys": (),
        "title_prefix_keys": _normalized_nonempty_tuple("Kobold"),
        "title_suffix_keys": (),
    },
    normalize_lookup("Mind Flayers: Scourge of Worlds"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": (),
        "title_keys": _normalized_nonempty_tuple(
            "Alhoon",
            "Elder Brain",
            "Intellect Devourer",
            "Mind Flayer",
            "Mindwitness",
            "Neothelid",
            "Ulitharid",
        ),
        "title_prefix_keys": _normalized_nonempty_tuple("Mind Flayer"),
        "title_suffix_keys": (),
    },
    normalize_lookup("Orcs: The Godsworn"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("orc"),
        "title_keys": _normalized_nonempty_tuple("Orc"),
        "title_prefix_keys": (),
        "title_suffix_keys": (),
    },
    normalize_lookup("Yuan-ti: Snake People"): {
        "group_keys": (),
        "type_keys": (),
        "tag_keys": _normalized_nonempty_tuple("yuan-ti"),
        "title_keys": (),
        "title_prefix_keys": _normalized_nonempty_tuple("Yuan-ti"),
        "title_suffix_keys": (),
    },
}


def _systems_service_request_cache() -> dict[tuple[object, ...], object] | None:
    if not has_request_context():
        return None
    cache = getattr(g, "_systems_service_request_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    g._systems_service_request_cache = cache
    return cache


def _systems_service_cache_get(cache_key: tuple[object, ...], build_value):
    cache = _systems_service_request_cache()
    if cache is None:
        return build_value()
    if cache_key not in cache:
        cache[cache_key] = build_value()
    return cache[cache_key]

ABILITY_NAME_LABELS = {
    "str": "Strength",
    "dex": "Dexterity",
    "con": "Constitution",
    "int": "Intelligence",
    "wis": "Wisdom",
    "cha": "Charisma",
}

DND_5E_SOURCE_CATALOG = (
    {
        "source_id": DND5E_RULES_REFERENCE_SOURCE_ID,
        "title": DND5E_RULES_REFERENCE_SOURCE_TITLE,
        "license_class": "open_license",
        "public_visibility_allowed": True,
        "requires_unofficial_notice": False,
        "default_visibility": VISIBILITY_PLAYERS,
        "enabled_by_default": True,
    },
    {
        "source_id": "PHB",
        "title": "Player's Handbook (2014)",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "DMG",
        "title": "Dungeon Master's Guide (2014)",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
        "book_entry_default_visibility": VISIBILITY_DM,
        "book_entry_policy_note": (
            "DMG chapter-backed rules pages default to DM visibility even if a campaign lowers "
            "the broader DMG source to surface specific player-facing DMG rows. Use entry "
            "overrides only when a chapter page should be intentionally exposed more broadly."
        ),
        "rules_reference_search_scope": RULES_REFERENCE_SEARCH_SCOPE_SOURCE_ONLY,
    },
    {
        "source_id": "MM",
        "title": "Monster Manual (2014)",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
    },
    {
        "source_id": "VGM",
        "title": "Volo's Guide to Monsters",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
    },
    {
        "source_id": "SCAG",
        "title": "Sword Coast Adventurer's Guide",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "XGE",
        "title": "Xanathar's Guide to Everything",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "TCE",
        "title": "Tasha's Cauldron of Everything",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
    {
        "source_id": "MTF",
        "title": "Mordenkainen's Tome of Foes",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_DM,
    },
    {
        "source_id": "EGW",
        "title": "Explorer's Guide to Wildemount",
        "license_class": "proprietary_private",
        "public_visibility_allowed": False,
        "requires_unofficial_notice": True,
        "default_visibility": VISIBILITY_PLAYERS,
    },
)

BUILTIN_LIBRARY_CATALOG = {
    "DND-5E": {
        "title": "DND 5E",
        "system_code": "DND-5E",
        "sources": DND_5E_SOURCE_CATALOG,
    }
}


class SystemsPolicyValidationError(ValueError):
    pass


@dataclass(slots=True)
class CampaignSourceState:
    source: SystemsSourceRecord
    is_enabled: bool
    default_visibility: str
    is_configured: bool


@dataclass(slots=True)
class SystemsMonsterCombatSeed:
    entry_key: str
    title: str
    source_id: str
    max_hp: int
    movement_total: int
    speed_label: str
    initiative_bonus: int


class SystemsService:
    def __init__(self, store: SystemsStore, repository_store: RepositoryStore) -> None:
        self.store = store
        self.repository_store = repository_store

    def ensure_builtin_library_seeded(self, library_slug: str) -> SystemsLibraryRecord | None:
        catalog = BUILTIN_LIBRARY_CATALOG.get(library_slug)
        existing_library = self.store.get_library(library_slug)
        if catalog is None:
            return existing_library

        # Normal page loads should not rewrite the Systems catalog on every read.
        library = existing_library
        if library is None:
            library = self.store.upsert_library(
                library_slug,
                title=str(catalog["title"]),
                system_code=str(catalog["system_code"]),
            )
        existing_source_ids = {
            source.source_id
            for source in self.store.list_sources(library_slug)
        }
        for source in catalog["sources"]:
            source_id = str(source["source_id"])
            if source_id in existing_source_ids:
                continue
            self.store.upsert_source(
                library_slug,
                source_id,
                title=str(source["title"]),
                license_class=str(source["license_class"]),
                public_visibility_allowed=bool(source.get("public_visibility_allowed", False)),
                requires_unofficial_notice=bool(source.get("requires_unofficial_notice", True)),
            )
        self._ensure_builtin_reference_entries_seeded(library.library_slug)
        return library

    def get_campaign_library_slug(self, campaign_slug: str) -> str:
        campaign = self._get_campaign(campaign_slug)
        if campaign is None:
            return ""
        if campaign.systems_library_slug:
            return campaign.systems_library_slug
        return campaign.system.strip()

    def get_campaign_library(self, campaign_slug: str) -> SystemsLibraryRecord | None:
        library_slug = self.get_campaign_library_slug(campaign_slug)
        if not library_slug:
            return None
        return self.ensure_builtin_library_seeded(library_slug)

    def get_campaign_policy(self, campaign_slug: str) -> CampaignSystemsPolicyRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        policy = self.store.get_campaign_policy(campaign_slug)
        if policy is not None:
            return policy
        now = utcnow()
        return CampaignSystemsPolicyRecord(
            campaign_slug=campaign_slug,
            library_slug=library.library_slug,
            status="active",
            proprietary_acknowledged_at=None,
            proprietary_acknowledged_by_user_id=None,
            created_at=now,
            updated_at=now,
            updated_by_user_id=None,
        )

    def list_campaign_source_states(self, campaign_slug: str) -> list[CampaignSourceState]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []
        configured_by_id = {
            item.source_id: item
            for item in self.store.list_campaign_enabled_sources(campaign_slug)
            if item.library_slug == library.library_slug
        }
        seed_by_id = self._campaign_source_seed_map(campaign_slug)
        rows: list[CampaignSourceState] = []
        for source in self.store.list_sources(library.library_slug):
            configured = configured_by_id.get(source.source_id)
            seed = seed_by_id.get(source.source_id, {})
            if configured is not None:
                is_enabled = configured.is_enabled
                default_visibility = configured.default_visibility
                is_configured = True
            else:
                is_enabled = (
                    bool(seed.get("enabled"))
                    if "enabled" in seed
                    else self._default_enabled_for_source(source)
                )
                default_visibility = self._normalize_or_default_visibility(
                    seed.get("default_visibility"),
                    fallback=self._default_visibility_for_source(source),
                )
                is_configured = False
            rows.append(
                CampaignSourceState(
                    source=source,
                    is_enabled=is_enabled,
                    default_visibility=self.clamp_visibility_for_source(source, default_visibility),
                    is_configured=is_configured,
                )
            )
        return rows

    def get_campaign_source_state(self, campaign_slug: str, source_id: str) -> CampaignSourceState | None:
        normalized_source_id = source_id.strip()
        for row in self.list_campaign_source_states(campaign_slug):
            if row.source.source_id == normalized_source_id:
                return row
        return None

    def list_entry_type_counts_for_campaign_source(
        self,
        campaign_slug: str,
        source_id: str,
    ) -> list[tuple[str, int]]:
        state = self.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            return []
        return self.store.list_entry_type_counts_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
        )

    def list_entries_for_campaign_source(
        self,
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        state = self.get_campaign_source_state(campaign_slug, source_id)
        if state is None or not state.is_enabled:
            return []
        entries = self.store.list_entries_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
            entry_type=entry_type,
            query=query,
            limit=limit,
        )
        if any(entry.entry_type == "book" for entry in entries):
            return sorted(entries, key=self._entry_source_browse_sort_key)
        return entries

    def list_enabled_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        entry_type: str | None = None,
        query: str = "",
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []

        normalized_query = str(query or "").strip()

        def _load_entries() -> list[SystemsEntryRecord]:
            enabled_source_ids = [
                str(row.source.source_id or "").strip()
                for row in self.list_campaign_source_states(campaign_slug)
                if row.is_enabled and str(row.source.source_id or "").strip()
            ]
            if not enabled_source_ids:
                return []
            return self.store.list_entries_for_campaign(
                campaign_slug,
                library.library_slug,
                enabled_source_ids,
                entry_type=entry_type,
                query=normalized_query,
                limit=limit,
            )

        return list(
            _systems_service_cache_get(
                (
                    "enabled-entries",
                    campaign_slug,
                    library.library_slug,
                    entry_type or "",
                    normalized_query,
                    limit,
                ),
                _load_entries,
            )
            or []
        )

    def count_entries_for_source(
        self,
        campaign_slug: str,
        source_id: str,
        *,
        entry_type: str | None = None,
    ) -> int:
        state = self.get_campaign_source_state(campaign_slug, source_id)
        if state is None:
            return 0
        return self.store.count_entries_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
            entry_type=entry_type,
        )

    def build_class_feature_progression_for_class_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []
        matching_entries = [
            candidate
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type="classfeature",
                limit=None,
            )
            if str(candidate.metadata.get("class_name", "") or "").strip() == entry.title
            and str(candidate.metadata.get("class_source", "") or "").strip().upper() == entry.source_id
        ]

        progression_rows = entry.body.get("feature_progression")
        matching_entries.extend(
            self._campaign_progression_entries_for_class_entry(campaign_slug, entry)
        )
        return self._build_feature_progression_groups(
            campaign_slug,
            matching_entries=matching_entries,
            progression_rows=progression_rows,
        )

    def build_subclass_feature_progression_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "subclass":
            return []
        class_name = str(entry.metadata.get("class_name", "") or "").strip()
        class_source = str(entry.metadata.get("class_source", "") or "").strip().upper()
        matching_entries = [
            candidate
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type="subclassfeature",
                limit=None,
            )
            if str(candidate.metadata.get("class_name", "") or "").strip() == class_name
            and str(candidate.metadata.get("class_source", "") or "").strip().upper() == class_source
            and self._subclass_entry_matches_feature(entry, candidate)
            and str(candidate.metadata.get("subclass_source", "") or "").strip().upper() == entry.source_id
        ]

        progression_rows = entry.body.get("feature_progression")
        matching_entries.extend(
            self._campaign_progression_entries_for_subclass_entry(campaign_slug, entry)
        )
        return self._build_feature_progression_groups(
            campaign_slug,
            matching_entries=matching_entries,
            progression_rows=progression_rows,
        )

    def _subclass_entry_matches_feature(
        self,
        subclass_entry: SystemsEntryRecord,
        subclass_feature_entry: SystemsEntryRecord,
    ) -> bool:
        subclass_title_variants = self._build_optionalfeature_title_variants(subclass_entry.title)
        feature_subclass_name = str(subclass_feature_entry.metadata.get("subclass_name", "") or "").strip()
        feature_title_variants = self._build_optionalfeature_title_variants(feature_subclass_name)
        return self._optionalfeature_titles_exactly_match(
            subclass_title_variants,
            feature_title_variants,
        ) or self._optionalfeature_titles_loosely_match(
            subclass_title_variants,
            feature_title_variants,
        )

    def build_class_starting_proficiency_rows(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []

        raw_rows = entry.body.get("starting_proficiencies")
        if not isinstance(raw_rows, list):
            return []

        skill_lookup = self._build_skill_entry_lookup(campaign_slug)
        rows: list[dict[str, object]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                continue
            name = str(raw_row.get("name", "") or "").strip()
            if not name:
                continue
            rows.append(
                {
                    "name": name,
                    "blocks": self._build_class_proficiency_blocks(
                        raw_row.get("entries"),
                        skill_lookup=skill_lookup if name.lower() == "skills" else None,
                    ),
                }
            )
        return [row for row in rows if row["blocks"]]

    def build_class_optionalfeature_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        class_feature_progression_groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if entry.entry_type != "class":
            return []

        raw_progression = entry.metadata.get("optionalfeature_progression")
        if not isinstance(raw_progression, list):
            return []

        feature_type_lookup = self._build_optionalfeature_feature_type_lookup(campaign_slug)
        optionalfeature_lookup = self._build_optionalfeature_entry_lookup(campaign_slug)
        standalone_sections: list[dict[str, object]] = []
        for raw_section in raw_progression:
            section = self._build_class_optionalfeature_section(
                campaign_slug,
                raw_section,
                feature_type_lookup=feature_type_lookup,
                optionalfeature_lookup=optionalfeature_lookup,
            )
            if section is None:
                continue
            if not self._attach_optionalfeature_section_to_matching_class_feature(
                section,
                class_feature_progression_groups,
            ):
                standalone_sections.append(section)
        return standalone_sections

    def build_subclass_optionalfeature_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        subclass_feature_progression_groups: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if entry.entry_type != "subclass":
            return []

        raw_progression = entry.metadata.get("optionalfeature_progression")
        if not isinstance(raw_progression, list):
            return []

        feature_type_lookup = self._build_optionalfeature_feature_type_lookup(campaign_slug)
        optionalfeature_lookup = self._build_optionalfeature_entry_lookup(campaign_slug)
        standalone_sections: list[dict[str, object]] = []
        for raw_section in raw_progression:
            section = self._build_class_optionalfeature_section(
                campaign_slug,
                raw_section,
                feature_type_lookup=feature_type_lookup,
                optionalfeature_lookup=optionalfeature_lookup,
            )
            if section is None:
                continue
            if not self._attach_optionalfeature_section_to_matching_class_feature(
                section,
                subclass_feature_progression_groups,
            ):
                standalone_sections.append(section)
        return standalone_sections

    def build_feature_detail_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> dict[str, object] | None:
        if entry.entry_type not in {"classfeature", "subclassfeature", "optionalfeature"}:
            return None
        return self._build_embedded_feature_card(
            campaign_slug,
            entry,
            optionalfeature_lookup=self._build_optionalfeature_entry_lookup(campaign_slug),
        )

    def build_character_sheet_entry_body_html(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> str:
        body_entries = entry.body.get("entries")
        if body_entries is not None:
            body_html, _ = self._render_embedded_content(
                campaign_slug,
                body_entries,
                heading_level=5,
                extract_option_groups=False,
                optionalfeature_lookup=self._build_optionalfeature_entry_lookup(campaign_slug),
                preferred_source_id=entry.source_id,
            )
            if body_html.strip():
                return body_html

        if entry.entry_type == "class":
            progression_html = self._render_character_sheet_progression_groups(
                self.build_class_feature_progression_for_class_entry(campaign_slug, entry),
            )
            if progression_html:
                return progression_html
        if entry.entry_type == "subclass":
            progression_html = self._render_character_sheet_progression_groups(
                self.build_subclass_feature_progression_for_subclass_entry(campaign_slug, entry),
            )
            if progression_html:
                return progression_html

        return self._strip_systems_entry_summary_section(entry.rendered_html)

    def get_entry_by_slug_for_campaign(self, campaign_slug: str, entry_slug: str) -> SystemsEntryRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        return self.store.get_entry_by_slug(library.library_slug, entry_slug.strip())

    def get_entry_for_campaign(self, campaign_slug: str, entry_key: str) -> SystemsEntryRecord | None:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return None
        entry = self.store.get_entry(library.library_slug, entry_key.strip())
        if entry is None or not self.is_entry_enabled_for_campaign(campaign_slug, entry):
            return None
        return entry

    def build_related_rules_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.source_id == DND5E_RULES_REFERENCE_SOURCE_ID or entry.entry_type == "rule":
            return []

        rules_by_key = self._build_rules_reference_lookup(campaign_slug)
        if not rules_by_key:
            return []

        rule_keys = self._collect_related_rule_keys_for_entry(entry)
        return self._resolve_rule_entries_by_key(rules_by_key, rule_keys)

    def build_related_monsters_for_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        if entry.entry_type != "book":
            return []
        if str(entry.source_id or "").strip().upper() != "VGM":
            return []
        matcher = VGM_MONSTER_LORE_WRAPPER_MONSTER_MATCHERS.get(normalize_lookup(entry.title))
        if not matcher:
            return []

        def build_value() -> list[SystemsEntryRecord]:
            related_entries: list[SystemsEntryRecord] = []
            seen_entry_keys: set[str] = set()
            for candidate in self.list_enabled_entries_for_campaign(
                campaign_slug,
                entry_type="monster",
                limit=None,
            ):
                if str(candidate.source_id or "").strip().upper() not in {"MM", "VGM"}:
                    continue
                if candidate.entry_key in seen_entry_keys:
                    continue
                if not self._monster_entry_matches_family(candidate, matcher):
                    continue
                seen_entry_keys.add(candidate.entry_key)
                related_entries.append(candidate)
            return sorted(
                related_entries,
                key=lambda candidate: (
                    *self._source_catalog_sort_key(candidate.source_id),
                    self._coerce_int(candidate.source_page, default=10_000),
                    candidate.title.lower(),
                    candidate.id,
                ),
            )

        return _systems_service_cache_get(
            ("related_monsters_for_entry", campaign_slug, entry.entry_key),
            build_value,
        )

    def build_related_rules_for_book_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> dict[str, list[SystemsEntryRecord]]:
        if entry.entry_type != "book" or str(entry.source_id or "").strip().upper() != "PHB":
            return {}

        raw_outline = (entry.metadata or {}).get("section_outline")
        if not isinstance(raw_outline, list) or not raw_outline:
            return {}

        rules_by_key = self._build_rules_reference_lookup(campaign_slug)
        if not rules_by_key:
            return {}

        related_by_anchor: dict[str, list[SystemsEntryRecord]] = {}
        for item in raw_outline:
            if not isinstance(item, dict):
                continue
            anchor = str(item.get("anchor") or "").strip()
            if not anchor:
                continue
            rule_keys = PHB_BOOK_SECTION_RULE_KEY_MAP.get(anchor, ())
            if not rule_keys:
                continue
            related_entries = self._resolve_rule_entries_by_key(rules_by_key, rule_keys)
            if related_entries:
                related_by_anchor[anchor] = related_entries
        return related_by_anchor

    def build_related_entities_for_book_sections(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> dict[str, list[dict[str, object]]]:
        if entry.entry_type != "book":
            return {}

        raw_outline = (entry.metadata or {}).get("section_outline")
        if not isinstance(raw_outline, list) or not raw_outline:
            return {}

        body_entries = dict(entry.body or {}).get("entries")
        if body_entries in (None, "", [], {}):
            return {}

        visible_anchors = {
            str(item.get("anchor") or "").strip()
            for item in raw_outline
            if isinstance(item, dict) and str(item.get("anchor") or "").strip()
        }
        if not visible_anchors:
            return {}

        related_refs_by_anchor: dict[str, list[dict[str, str | None]]] = defaultdict(list)
        self._collect_book_section_entity_refs(
            body_entries,
            current_path=(),
            visible_anchors=visible_anchors,
            related_refs_by_anchor=related_refs_by_anchor,
        )
        if not related_refs_by_anchor:
            return {}

        entries_by_identity, exact_title_lookup = self._build_book_section_entity_lookups(campaign_slug)
        if not entries_by_identity and not exact_title_lookup:
            return {}

        current_source_id = str(entry.source_id or "").strip().upper()
        related_by_anchor: dict[str, list[dict[str, object]]] = {}
        for anchor, related_refs in related_refs_by_anchor.items():
            grouped_entries = self._resolve_book_section_entity_refs(
                related_refs,
                current_source_id=current_source_id,
                entries_by_identity=entries_by_identity,
                exact_title_lookup=exact_title_lookup,
            )
            if not grouped_entries:
                continue
            related_by_anchor[anchor] = grouped_entries
        return related_by_anchor

    def _build_rules_reference_lookup(self, campaign_slug: str) -> dict[str, SystemsEntryRecord]:
        rows = self.list_entries_for_campaign_source(
            campaign_slug,
            DND5E_RULES_REFERENCE_SOURCE_ID,
            entry_type="rule",
            limit=None,
        )
        lookup: dict[str, SystemsEntryRecord] = {}
        for entry in rows:
            metadata = dict(entry.metadata or {})
            rule_key = str(metadata.get("rule_key") or "").strip() or normalize_lookup(entry.title)
            if rule_key:
                lookup[rule_key] = entry
        return lookup

    def _resolve_rule_entries_by_key(
        self,
        rules_by_key: dict[str, SystemsEntryRecord],
        rule_keys: list[str] | tuple[str, ...],
    ) -> list[SystemsEntryRecord]:
        related_entries: list[SystemsEntryRecord] = []
        seen_entry_keys: set[str] = set()
        for rule_key in rule_keys:
            entry = rules_by_key.get(str(rule_key or "").strip())
            if entry is None or entry.entry_key in seen_entry_keys:
                continue
            seen_entry_keys.add(entry.entry_key)
            related_entries.append(entry)
        return related_entries

    def _monster_entry_matches_family(
        self,
        entry: SystemsEntryRecord,
        matcher: dict[str, tuple[str, ...]],
    ) -> bool:
        if entry.entry_type != "monster":
            return False

        title_key = normalize_lookup(entry.title)
        if title_key and title_key in matcher.get("title_keys", ()):
            return True
        if title_key and any(
            title_key.startswith(prefix_key) for prefix_key in matcher.get("title_prefix_keys", ())
        ):
            return True
        if title_key and any(
            title_key.endswith(suffix_key) for suffix_key in matcher.get("title_suffix_keys", ())
        ):
            return True

        metadata = dict(entry.metadata or {})
        group_keys = self._monster_metadata_group_keys(metadata.get("group"))
        if group_keys.intersection(matcher.get("group_keys", ())):
            return True

        type_keys, tag_keys = self._monster_metadata_type_keys(metadata.get("type"))
        if type_keys.intersection(matcher.get("type_keys", ())):
            return True
        if tag_keys.intersection(matcher.get("tag_keys", ())):
            return True
        return False

    def _monster_metadata_group_keys(self, value: object) -> set[str]:
        keys: set[str] = set()
        raw_values = value if isinstance(value, list) else [value]
        for raw_value in raw_values:
            normalized_value = normalize_lookup(str(raw_value or ""))
            if normalized_value:
                keys.add(normalized_value)
        return keys

    def _monster_metadata_type_keys(self, value: object) -> tuple[set[str], set[str]]:
        type_keys: set[str] = set()
        tag_keys: set[str] = set()
        raw_values = value if isinstance(value, list) else [value]
        for raw_value in raw_values:
            if isinstance(raw_value, dict):
                normalized_type = normalize_lookup(str(raw_value.get("type") or ""))
                if normalized_type:
                    type_keys.add(normalized_type)
                raw_tags = raw_value.get("tags")
                tag_values = raw_tags if isinstance(raw_tags, list) else [raw_tags]
                for raw_tag in tag_values:
                    if isinstance(raw_tag, dict):
                        raw_tag = raw_tag.get("tag") or raw_tag.get("name") or raw_tag.get("value")
                    normalized_tag = normalize_lookup(str(raw_tag or ""))
                    if normalized_tag:
                        tag_keys.add(normalized_tag)
                continue

            normalized_type = normalize_lookup(str(raw_value or ""))
            if normalized_type:
                type_keys.add(normalized_type)
        return type_keys, tag_keys

    def _build_book_section_entity_lookups(
        self,
        campaign_slug: str,
    ) -> tuple[dict[tuple[str, str, str], SystemsEntryRecord], dict[tuple[str, str], list[SystemsEntryRecord]]]:
        def build_value():
            enabled_source_ids = [
                str(row.source.source_id or "").strip().upper()
                for row in self.list_campaign_source_states(campaign_slug)
                if row.is_enabled
            ]
            entries_by_identity: dict[tuple[str, str, str], SystemsEntryRecord] = {}
            exact_title_lookup: dict[tuple[str, str], list[SystemsEntryRecord]] = defaultdict(list)
            for source_id in enabled_source_ids:
                for entry_type in BOOK_SECTION_ENTITY_TYPE_ORDER:
                    for entry in self.list_entries_for_campaign_source(
                        campaign_slug,
                        source_id,
                        entry_type=entry_type,
                        limit=None,
                    ):
                        normalized_title = normalize_lookup(entry.title)
                        if not normalized_title:
                            continue
                        entries_by_identity.setdefault((source_id, entry_type, normalized_title), entry)
                        exact_title_lookup[(source_id, normalized_title)].append(entry)
            return entries_by_identity, dict(exact_title_lookup)

        return _systems_service_cache_get(
            ("book_section_entity_lookups", campaign_slug),
            build_value,
        )

    def _resolve_book_section_entity_refs(
        self,
        related_refs: list[dict[str, str | None]],
        *,
        current_source_id: str,
        entries_by_identity: dict[tuple[str, str, str], SystemsEntryRecord],
        exact_title_lookup: dict[tuple[str, str], list[SystemsEntryRecord]],
    ) -> list[dict[str, object]]:
        grouped_entries: dict[str, list[SystemsEntryRecord]] = defaultdict(list)
        seen_entry_keys: set[str] = set()
        for related_ref in related_refs:
            entry = self._resolve_book_section_entity_ref(
                related_ref,
                current_source_id=current_source_id,
                entries_by_identity=entries_by_identity,
                exact_title_lookup=exact_title_lookup,
            )
            if entry is None or entry.entry_key in seen_entry_keys:
                continue
            seen_entry_keys.add(entry.entry_key)
            grouped_entries[entry.entry_type].append(entry)

        groups: list[dict[str, object]] = []
        for entry_type in BOOK_SECTION_ENTITY_TYPE_ORDER:
            entries = grouped_entries.get(entry_type, [])
            if not entries:
                continue
            groups.append(
                {
                    "label": BOOK_SECTION_ENTITY_GROUP_LABELS.get(
                        entry_type,
                        entry_type.replace("_", " ").title(),
                    ),
                    "entries": entries,
                }
            )
        return groups

    def _resolve_book_section_entity_ref(
        self,
        related_ref: dict[str, str | None],
        *,
        current_source_id: str,
        entries_by_identity: dict[tuple[str, str, str], SystemsEntryRecord],
        exact_title_lookup: dict[tuple[str, str], list[SystemsEntryRecord]],
    ) -> SystemsEntryRecord | None:
        normalized_title = str(related_ref.get("title") or "").strip()
        if not normalized_title:
            return None
        explicit_source_id = str(related_ref.get("source_id") or "").strip().upper()
        entry_type = str(related_ref.get("entry_type") or "").strip().lower() or None
        source_ids = (
            (explicit_source_id,)
            if explicit_source_id
            else self._candidate_book_section_entity_source_ids(
                current_source_id=current_source_id,
                entry_type=entry_type,
            )
        )
        if not source_ids:
            return None

        if entry_type:
            for source_id in source_ids:
                entry = entries_by_identity.get((source_id, entry_type, normalized_title))
                if entry is not None:
                    return entry
            return None

        for source_id in source_ids:
            candidates = exact_title_lookup.get((source_id, normalized_title), [])
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _candidate_book_section_entity_source_ids(
        self,
        *,
        current_source_id: str,
        entry_type: str | None,
    ) -> tuple[str, ...]:
        normalized_source_id = str(current_source_id or "").strip().upper()
        if not normalized_source_id:
            return ()

        candidate_source_ids = [normalized_source_id]
        fallback_by_type = BOOK_SECTION_ENTITY_SOURCE_FALLBACKS.get(normalized_source_id, {})
        fallback_types = (entry_type,) if entry_type else BOOK_SECTION_ENTITY_TYPE_ORDER
        for fallback_type in fallback_types:
            normalized_fallback_type = str(fallback_type or "").strip().lower()
            if not normalized_fallback_type:
                continue
            for fallback_source_id in fallback_by_type.get(normalized_fallback_type, ()):
                normalized_fallback_source_id = str(fallback_source_id or "").strip().upper()
                if (
                    normalized_fallback_source_id
                    and normalized_fallback_source_id not in candidate_source_ids
                ):
                    candidate_source_ids.append(normalized_fallback_source_id)
        return tuple(candidate_source_ids)

    def _collect_book_section_entity_refs(
        self,
        value: object,
        *,
        current_path: tuple[str, ...],
        visible_anchors: set[str],
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
    ) -> None:
        if value is None:
            return
        current_anchor = self._resolve_visible_book_section_anchor(current_path, visible_anchors)
        if isinstance(value, str):
            self._collect_inline_book_section_entity_refs(
                value,
                visible_anchor=current_anchor,
                related_refs_by_anchor=related_refs_by_anchor,
            )
            return
        if isinstance(value, list):
            for item in value:
                self._collect_book_section_entity_refs(
                    item,
                    current_path=current_path,
                    visible_anchors=visible_anchors,
                    related_refs_by_anchor=related_refs_by_anchor,
                )
            return
        if not isinstance(value, dict):
            return

        next_path = current_path
        if self._is_book_navigation_section(value):
            name = self._clean_embedded_text(str(value.get("name", "") or ""))
            if name:
                next_path = (*current_path, name)
        next_anchor = self._resolve_visible_book_section_anchor(next_path, visible_anchors)
        self._collect_named_book_section_entity_refs(
            value,
            visible_anchor=next_anchor,
            related_refs_by_anchor=related_refs_by_anchor,
        )

        value_type = str(value.get("type", "") or "").strip().lower()
        nested_values: list[object] = []
        if value_type == "list":
            nested_values.append(value.get("items"))
        elif value_type == "table":
            nested_values.append(value.get("rows"))
            nested_values.append(value.get("rowsSpellProgression"))
        elif value_type == "options":
            nested_values.append(value.get("entries"))
        else:
            if value.get("entries") is not None:
                nested_values.append(value.get("entries"))
            elif value.get("entry") is not None:
                nested_values.append(value.get("entry"))
        for nested_value in nested_values:
            self._collect_book_section_entity_refs(
                nested_value,
                current_path=next_path,
                visible_anchors=visible_anchors,
                related_refs_by_anchor=related_refs_by_anchor,
            )

    def _collect_inline_book_section_entity_refs(
        self,
        value: str,
        *,
        visible_anchor: str | None,
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
    ) -> None:
        if not visible_anchor:
            return
        for match in INLINE_TAG_PATTERN.finditer(str(value or "")):
            body = match.group(1).strip()
            tag, _, remainder = body.partition(" ")
            entry_type = BOOK_SECTION_ENTITY_TAG_ENTRY_TYPES.get(tag.lower().strip())
            if not entry_type or not remainder.strip():
                continue
            title, source_id = self._parse_book_section_entity_reference(remainder)
            if not title:
                continue
            self._append_book_section_entity_ref(
                related_refs_by_anchor,
                visible_anchor=visible_anchor,
                entry_type=entry_type,
                title=title,
                source_id=source_id,
            )

    def _collect_named_book_section_entity_refs(
        self,
        value: dict[str, object],
        *,
        visible_anchor: str | None,
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
    ) -> None:
        if not visible_anchor:
            return

        candidate_titles: list[str] = []
        name = self._clean_embedded_text(str(value.get("name", "") or ""))
        if name:
            candidate_titles.append(name)

        raw_aliases = value.get("alias")
        alias_values = raw_aliases if isinstance(raw_aliases, list) else [raw_aliases]
        for raw_alias in alias_values:
            alias = self._clean_embedded_text(str(raw_alias or ""))
            if alias:
                candidate_titles.append(alias)

        for title in candidate_titles:
            self._append_book_section_entity_ref(
                related_refs_by_anchor,
                visible_anchor=visible_anchor,
                entry_type=None,
                title=title,
                source_id=None,
            )

    def _append_book_section_entity_ref(
        self,
        related_refs_by_anchor: dict[str, list[dict[str, str | None]]],
        *,
        visible_anchor: str,
        entry_type: str | None,
        title: str,
        source_id: str | None,
    ) -> None:
        normalized_title = normalize_lookup(self._clean_embedded_text(str(title or "")))
        if not normalized_title:
            return
        normalized_source_id = str(source_id or "").strip().upper() or None
        related_refs_by_anchor.setdefault(visible_anchor, []).append(
            {
                "entry_type": entry_type,
                "title": normalized_title,
                "source_id": normalized_source_id,
            }
        )

    def _parse_book_section_entity_reference(self, raw_reference: str) -> tuple[str, str | None]:
        parts = [part.strip() for part in str(raw_reference or "").split("|")]
        if not parts:
            return "", None
        title = self._clean_embedded_text(parts[0])
        source_id = parts[1].upper() if len(parts) > 1 and parts[1] else None
        return title, source_id

    def _resolve_visible_book_section_anchor(
        self,
        current_path: tuple[str, ...],
        visible_anchors: set[str],
    ) -> str | None:
        if not current_path or not visible_anchors:
            return None
        for length in range(len(current_path), 0, -1):
            anchor = self._build_book_section_anchor(current_path[:length])
            if anchor in visible_anchors:
                return anchor
        return None

    def _build_book_section_anchor(self, path: tuple[str, ...]) -> str:
        parts: list[str] = []
        for item in path:
            cleaned_item = self._clean_embedded_text(str(item or ""))
            if not cleaned_item:
                continue
            anchor_part = slugify(cleaned_item).replace("/", "-") or normalize_lookup(cleaned_item)
            if anchor_part:
                parts.append(anchor_part)
        return "--".join(parts) or "book-section"

    def _is_book_navigation_section(self, value: object) -> bool:
        if not isinstance(value, dict):
            return False
        value_type = str(value.get("type", "") or "").strip().lower()
        if value_type not in {"", "section", "entries"}:
            return False
        if not self._clean_embedded_text(str(value.get("name", "") or "")):
            return False
        return value.get("entries") is not None or value.get("entry") is not None

    def _collect_related_rule_keys_for_entry(self, entry: SystemsEntryRecord) -> list[str]:
        metadata = dict(entry.metadata or {})
        title_key = normalize_lookup(entry.title)
        entry_type = str(entry.entry_type or "").strip().lower()
        rule_keys: list[str] = []

        def add_rule_key(rule_key: str) -> None:
            normalized_rule_key = str(rule_key or "").strip()
            if normalized_rule_key and normalized_rule_key not in rule_keys:
                rule_keys.append(normalized_rule_key)

        if entry_type == "skill":
            add_rule_key("ability-scores-and-ability-modifiers")
            add_rule_key("proficiency-bonus")
            add_rule_key("skill-bonuses-and-proficiency")
            if title_key in PASSIVE_CHECK_SKILL_KEYS:
                add_rule_key("passive-checks")
            return rule_keys

        if entry_type == "item":
            item_type = str(metadata.get("type") or "").strip().upper()
            is_armor = bool(metadata.get("armor")) or item_type in ARMOR_ITEM_TYPE_CODES or bool(metadata.get("ac"))
            is_weapon = item_type in WEAPON_ITEM_TYPE_CODES
            if is_armor:
                add_rule_key("armor-class")
            if is_weapon:
                add_rule_key("attack-rolls-and-attack-bonus")
                add_rule_key("damage-rolls")
            add_rule_key("equipped-items-inventory-and-attunement")
            return rule_keys

        if entry_type == "spell":
            add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type == "class":
            add_rule_key("proficiency-bonus")
            add_rule_key("hit-points-and-hit-dice")
            if self._entry_has_spellcasting_metadata(metadata):
                add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type == "subclass":
            if self._entry_has_spellcasting_metadata(metadata):
                add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type in {"classfeature", "subclassfeature", "feat", "optionalfeature"}:
            if metadata.get("additional_spells") is not None:
                add_rule_key("spell-attacks-and-save-dcs")
            return rule_keys

        if entry_type == "variantrule":
            if title_key == "encumbrance":
                add_rule_key("carrying-capacity-and-encumbrance")
            return rule_keys

        return rule_keys

    def _entry_has_spellcasting_metadata(self, metadata: dict[str, object]) -> bool:
        return any(
            metadata.get(key)
            for key in (
                "spellcasting_ability",
                "caster_progression",
                "prepared_spells",
                "prepared_spells_change",
                "prepared_spells_progression",
                "cantrip_progression",
                "spells_known_progression",
                "spells_known_progression_fixed",
                "slot_progression",
            )
        )

    def _entry_source_browse_sort_key(self, entry: SystemsEntryRecord) -> tuple[int, int, int, str, int]:
        if entry.entry_type == "book":
            return (
                0,
                self._coerce_int((entry.metadata or {}).get("chapter_index"), default=10_000),
                self._coerce_int(entry.source_page, default=10_000),
                entry.title.lower(),
                entry.id,
            )
        return (1, 10_000, 10_000, entry.title.lower(), entry.id)

    def _source_catalog_sort_key(self, source_id: str) -> tuple[int, str]:
        normalized_source_id = str(source_id or "").strip().upper()
        for index, source in enumerate(DND_5E_SOURCE_CATALOG):
            if str(source.get("source_id") or "").strip().upper() == normalized_source_id:
                return (index, normalized_source_id)
        return (len(DND_5E_SOURCE_CATALOG), normalized_source_id)

    def _source_catalog_entry(
        self,
        source: SystemsSourceRecord | str,
        *,
        library_slug: str | None = None,
    ) -> dict[str, object] | None:
        if isinstance(source, SystemsSourceRecord):
            library_slug = source.library_slug
            source_id = source.source_id
        else:
            source_id = str(source or "").strip()
        resolved_library_slug = str(library_slug or "DND-5E").strip()
        if not resolved_library_slug or not str(source_id or "").strip():
            return None
        catalog = BUILTIN_LIBRARY_CATALOG.get(resolved_library_slug, {})
        normalized_source_id = str(source_id or "").strip().upper()
        for item in catalog.get("sources", ()):
            if str(item.get("source_id") or "").strip().upper() == normalized_source_id:
                return dict(item)
        return None

    def get_rules_reference_search_scope_for_source(
        self,
        source: SystemsSourceRecord | str,
        *,
        library_slug: str | None = None,
    ) -> str:
        catalog_entry = self._source_catalog_entry(source, library_slug=library_slug)
        scope = str(
            (catalog_entry or {}).get(
                "rules_reference_search_scope",
                RULES_REFERENCE_SEARCH_SCOPE_GLOBAL,
            )
            or RULES_REFERENCE_SEARCH_SCOPE_GLOBAL
        ).strip().lower()
        if scope not in {
            RULES_REFERENCE_SEARCH_SCOPE_GLOBAL,
            RULES_REFERENCE_SEARCH_SCOPE_SOURCE_ONLY,
        }:
            return RULES_REFERENCE_SEARCH_SCOPE_GLOBAL
        return scope

    def get_default_entry_visibility_for_campaign(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> str:
        source_state = self.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None or not source_state.is_enabled:
            return VISIBILITY_PRIVATE
        default_visibility = source_state.default_visibility
        entry_default_visibility = self._entry_default_visibility_for_source(
            source_state.source,
            entry,
        )
        if entry_default_visibility:
            default_visibility = most_private_visibility(default_visibility, entry_default_visibility)
        return self.clamp_visibility_for_source(source_state.source, default_visibility)

    def get_book_entry_policy_note_for_source(
        self,
        source: SystemsSourceRecord | str,
        *,
        library_slug: str | None = None,
    ) -> str:
        catalog_entry = self._source_catalog_entry(source, library_slug=library_slug)
        return str((catalog_entry or {}).get("book_entry_policy_note") or "").strip()

    def _rules_reference_entry_sort_key(self, entry: SystemsEntryRecord) -> tuple[int, str, int, int, str, int]:
        return (*self._source_catalog_sort_key(entry.source_id), *self._entry_source_browse_sort_key(entry))

    def _normalize_source_filter(self, source_ids: list[str] | None) -> list[str] | None:
        if source_ids is None:
            return None
        normalized = [
            str(source_id or "").strip().upper()
            for source_id in list(source_ids or [])
            if str(source_id or "").strip()
        ]
        return normalized

    def _entry_default_visibility_for_source(
        self,
        source: SystemsSourceRecord,
        entry: SystemsEntryRecord,
    ) -> str:
        if entry.entry_type != "book":
            return ""
        catalog_entry = self._source_catalog_entry(source)
        default_visibility = normalize_visibility_choice(
            str((catalog_entry or {}).get("book_entry_default_visibility") or "")
        )
        if is_valid_visibility(default_visibility):
            return default_visibility
        return ""

    def _reference_search_values(self, value: object) -> list[str]:
        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                values.extend(self._reference_search_values(item))
            return values
        if isinstance(value, dict):
            values: list[str] = []
            for key in ("title", "label", "name"):
                cleaned = str(value.get(key) or "").strip()
                if cleaned:
                    values.append(cleaned)
            return values
        cleaned = str(value or "").strip()
        return [cleaned] if cleaned else []

    def _build_rules_reference_search_text(self, entry: SystemsEntryRecord) -> str:
        metadata = dict(entry.metadata or {})
        search_parts: list[str] = [entry.title, entry.source_id, entry.entry_type]
        if entry.entry_type == "book":
            search_parts.extend(
                [
                    str(metadata.get("section_label") or "").strip(),
                    *self._reference_search_values(metadata.get("headers")),
                    *self._reference_search_values(metadata.get("section_outline")),
                ]
            )
        elif entry.entry_type == "rule":
            search_parts.extend(
                [
                    str(metadata.get("rule_key") or "").strip(),
                    str(metadata.get("formula") or "").strip(),
                    *self._reference_search_values(metadata.get("aliases")),
                    *self._reference_search_values(metadata.get("rule_facets")),
                ]
            )
        search_parts.extend(self._reference_search_values(metadata.get("reference_terms")))
        return " ".join(normalize_lookup(part) for part in search_parts if str(part or "").strip())

    def list_rules_reference_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        include_source_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[SystemsEntryRecord]:
        normalized_source_ids = self._normalize_source_filter(include_source_ids)
        if include_source_ids is not None and not normalized_source_ids:
            return []

        entries: list[SystemsEntryRecord] = []
        for entry_type in RULES_REFERENCE_ENTRY_TYPES:
            entries.extend(
                self.list_enabled_entries_for_campaign(
                    campaign_slug,
                    entry_type=entry_type,
                    limit=None,
                )
            )
        if normalized_source_ids is not None:
            entries = [entry for entry in entries if str(entry.source_id or "").strip().upper() in normalized_source_ids]
        entries = sorted(entries, key=self._rules_reference_entry_sort_key)
        if limit is not None:
            return entries[:limit]
        return entries

    def search_rules_reference_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        query: str,
        include_source_ids: list[str] | None = None,
        limit: int | None = 100,
    ) -> list[SystemsEntryRecord]:
        normalized_terms = [
            normalize_lookup(term)
            for term in str(query or "").split()
            if normalize_lookup(term)
        ]
        if not normalized_terms:
            return []

        matches = [
            entry
            for entry in self.list_rules_reference_entries_for_campaign(
                campaign_slug,
                include_source_ids=include_source_ids,
                limit=None,
            )
            if all(term in self._build_rules_reference_search_text(entry) for term in normalized_terms)
        ]
        if limit is not None:
            return matches[:limit]
        return matches

    def list_monster_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        limit: int = 1000,
    ) -> list[SystemsEntryRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        if not enabled_source_ids:
            return []
        entries = self.store.list_entries(
            library.library_slug,
            source_ids=enabled_source_ids,
            entry_type="monster",
            limit=limit,
        )
        return [entry for entry in entries if self.is_entry_enabled_for_campaign(campaign_slug, entry)]

    def build_monster_combat_seed(self, entry: SystemsEntryRecord) -> SystemsMonsterCombatSeed:
        if entry.entry_type != "monster":
            raise ValueError("Only monster entries can seed combat NPCs.")
        metadata = dict(entry.metadata or {})
        abilities = dict(metadata.get("abilities") or {})
        dex_score = self._coerce_int(abilities.get("dex"), default=10)
        initiative_bonus = (dex_score - 10) // 2
        speed = metadata.get("speed")
        return SystemsMonsterCombatSeed(
            entry_key=entry.entry_key,
            title=entry.title,
            source_id=entry.source_id,
            max_hp=self._extract_monster_hp_average(metadata.get("hp")),
            movement_total=self._extract_max_distance(speed),
            speed_label=self._format_speed_label(speed),
            initiative_bonus=initiative_bonus,
        )

    def search_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        query: str,
        include_source_ids: list[str] | None = None,
        entry_type: str | None = None,
        limit: int = 100,
    ) -> list[SystemsEntryRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            return []

        enabled_source_ids = {
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        }
        if include_source_ids is not None:
            enabled_source_ids &= {str(source_id).strip() for source_id in include_source_ids if str(source_id).strip()}
        if not enabled_source_ids:
            return []

        entries = self.store.search_entries(
            library.library_slug,
            query=query,
            source_ids=sorted(enabled_source_ids),
            entry_type=entry_type,
            limit=limit,
        )
        return [entry for entry in entries if self.is_entry_enabled_for_campaign(campaign_slug, entry)]

    def search_monster_entries_for_campaign(
        self,
        campaign_slug: str,
        *,
        query: str,
        limit: int = 30,
    ) -> list[SystemsEntryRecord]:
        return self.search_entries_for_campaign(
            campaign_slug,
            query=query,
            entry_type="monster",
            limit=limit,
        )

    def is_entry_enabled_for_campaign(self, campaign_slug: str, entry: SystemsEntryRecord) -> bool:
        source_state = self.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None or not source_state.is_enabled:
            return False
        override = self.store.get_campaign_entry_override(campaign_slug, entry.entry_key)
        if override is not None and override.is_enabled_override is False:
            return False
        return True

    def update_campaign_sources(
        self,
        campaign_slug: str,
        *,
        updates: list[dict[str, object]],
        actor_user_id: int,
        acknowledge_proprietary: bool,
        can_set_private: bool,
    ) -> list[SystemsSourceRecord]:
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        current_policy = self.store.get_campaign_policy(campaign_slug)
        current_states = {row.source.source_id: row for row in self.list_campaign_source_states(campaign_slug)}
        source_records = {row.source.source_id: row.source for row in current_states.values()}
        normalized_updates: list[dict[str, object]] = []
        newly_enabled_proprietary = False
        for raw_update in updates:
            source_id = str(raw_update.get("source_id", "") or "").strip()
            source = source_records.get(source_id)
            if source is None:
                raise SystemsPolicyValidationError("Choose a valid systems source.")
            is_enabled = bool(raw_update.get("is_enabled", False))
            default_visibility = self._normalize_or_default_visibility(
                raw_update.get("default_visibility"),
                fallback=current_states[source_id].default_visibility,
            )
            if not is_valid_visibility(default_visibility):
                raise SystemsPolicyValidationError(f"Choose a valid visibility for {source.title}.")
            if default_visibility == VISIBILITY_PRIVATE and not can_set_private:
                raise SystemsPolicyValidationError("Private visibility is reserved for app admins.")
            if default_visibility == VISIBILITY_PUBLIC and not source.public_visibility_allowed:
                raise SystemsPolicyValidationError(
                    f"{source.title} cannot be made public because that source is marked as proprietary or otherwise non-public."
                )
            if (
                is_enabled
                and not current_states[source_id].is_enabled
                and source.license_class == "proprietary_private"
                and (current_policy is None or current_policy.proprietary_acknowledged_at is None)
            ):
                newly_enabled_proprietary = True
            normalized_updates.append(
                {
                    "source_id": source_id,
                    "is_enabled": is_enabled,
                    "default_visibility": self.clamp_visibility_for_source(source, default_visibility),
                }
            )

        if newly_enabled_proprietary and not acknowledge_proprietary:
            raise SystemsPolicyValidationError(
                "Acknowledge the proprietary-source notice before enabling a protected systems source."
            )

        self.store.upsert_campaign_policy(
            campaign_slug,
            library_slug=library.library_slug,
            proprietary_acknowledged_at=(
                isoformat(utcnow()) if newly_enabled_proprietary and acknowledge_proprietary else None
            ),
            proprietary_acknowledged_by_user_id=actor_user_id if newly_enabled_proprietary and acknowledge_proprietary else None,
            updated_by_user_id=actor_user_id,
        )

        changed_sources: list[SystemsSourceRecord] = []
        for update in normalized_updates:
            source_id = str(update["source_id"])
            current = current_states[source_id]
            if current.is_enabled == bool(update["is_enabled"]) and current.default_visibility == str(update["default_visibility"]) and current.is_configured:
                continue
            if current.is_enabled == bool(update["is_enabled"]) and current.default_visibility == str(update["default_visibility"]) and not current.is_configured:
                continue
            self.store.upsert_campaign_enabled_source(
                campaign_slug,
                library_slug=library.library_slug,
                source_id=source_id,
                is_enabled=bool(update["is_enabled"]),
                default_visibility=str(update["default_visibility"]),
                updated_by_user_id=actor_user_id,
            )
            source = source_records.get(source_id)
            if source is not None:
                changed_sources.append(source)
        return changed_sources

    def update_campaign_entry_override(
        self,
        campaign_slug: str,
        *,
        entry_key: str,
        visibility_override: str | None,
        is_enabled_override: bool | None,
        actor_user_id: int,
        can_set_private: bool,
    ):
        library = self.get_campaign_library(campaign_slug)
        if library is None:
            raise SystemsPolicyValidationError("That campaign does not have a systems library configured.")
        entry = self.store.get_entry(library.library_slug, entry_key.strip())
        if entry is None:
            raise SystemsPolicyValidationError("Choose a valid systems entry before saving an override.")
        source_state = self.get_campaign_source_state(campaign_slug, entry.source_id)
        if source_state is None:
            raise SystemsPolicyValidationError("That source is not available for this campaign.")
        normalized_visibility = None
        if visibility_override is not None and visibility_override != "":
            normalized_visibility = self._normalize_or_default_visibility(
                visibility_override,
                fallback=source_state.default_visibility,
            )
            if normalized_visibility == VISIBILITY_PRIVATE and not can_set_private:
                raise SystemsPolicyValidationError("Private visibility is reserved for app admins.")
            if normalized_visibility == VISIBILITY_PUBLIC and not source_state.source.public_visibility_allowed:
                raise SystemsPolicyValidationError(
                    f"{source_state.source.title} cannot be made public because that source is marked as proprietary or otherwise non-public."
                )
        self.store.upsert_campaign_policy(
            campaign_slug,
            library_slug=library.library_slug,
            updated_by_user_id=actor_user_id,
        )
        return self.store.upsert_campaign_entry_override(
            campaign_slug,
            library_slug=library.library_slug,
            entry_key=entry.entry_key,
            visibility_override=normalized_visibility,
            is_enabled_override=is_enabled_override,
            updated_by_user_id=actor_user_id,
        )

    def clamp_visibility_for_source(self, source: SystemsSourceRecord, visibility: str) -> str:
        normalized = self._normalize_or_default_visibility(
            visibility,
            fallback=self._default_visibility_for_source(source),
        )
        if normalized == VISIBILITY_PUBLIC and not source.public_visibility_allowed:
            return VISIBILITY_PLAYERS
        return normalized

    def _get_campaign(self, campaign_slug: str):
        return self.repository_store.get().get_campaign(campaign_slug)

    def _campaign_source_seed_map(self, campaign_slug: str) -> dict[str, dict[str, object]]:
        campaign = self._get_campaign(campaign_slug)
        if campaign is None:
            return {}
        seed_map: dict[str, dict[str, object]] = {}
        for item in campaign.systems_source_defaults:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id", "") or "").strip()
            if not source_id:
                continue
            seed_map[source_id] = dict(item)
        return seed_map

    def _default_visibility_for_source(self, source: SystemsSourceRecord) -> str:
        catalog = BUILTIN_LIBRARY_CATALOG.get(source.library_slug, {})
        for item in catalog.get("sources", ()):
            if item["source_id"] == source.source_id:
                return str(item.get("default_visibility", VISIBILITY_DM))
        return VISIBILITY_DM

    def _default_enabled_for_source(self, source: SystemsSourceRecord) -> bool:
        catalog = BUILTIN_LIBRARY_CATALOG.get(source.library_slug, {})
        for item in catalog.get("sources", ()):
            if item["source_id"] == source.source_id:
                return bool(item.get("enabled_by_default", False))
        return False

    def _ensure_builtin_reference_entries_seeded(self, library_slug: str) -> None:
        if library_slug != "DND-5E":
            return
        expected_entries = build_dnd5e_rules_reference_entries()
        sentinel_entry = self.store.get_entry(library_slug, DND5E_RULES_REFERENCE_SENTINEL_ENTRY_KEY)
        existing_count = self.store.count_entries_for_source(library_slug, DND5E_RULES_REFERENCE_SOURCE_ID)
        if (
            sentinel_entry is not None
            and sentinel_entry.source_id == DND5E_RULES_REFERENCE_SOURCE_ID
            and str((sentinel_entry.metadata or {}).get("seed_version") or "") == DND5E_RULES_REFERENCE_VERSION
            and existing_count == len(expected_entries)
        ):
            return
        self.store.replace_entries_for_source(
            library_slug,
            DND5E_RULES_REFERENCE_SOURCE_ID,
            entries=expected_entries,
        )

    def _normalize_or_default_visibility(self, value: object, *, fallback: str) -> str:
        normalized = normalize_visibility_choice(str(value or ""))
        if is_valid_visibility(normalized):
            return normalized
        return fallback

    def _build_skill_entry_lookup(self, campaign_slug: str) -> dict[str, SystemsEntryRecord]:
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        lookup: dict[str, SystemsEntryRecord] = {}
        for source_id in enabled_source_ids:
            for entry in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="skill",
                limit=None,
            ):
                lookup.setdefault(normalize_lookup(entry.title), entry)
        return lookup

    def _build_optionalfeature_entry_lookup(self, campaign_slug: str) -> dict[str, list[SystemsEntryRecord]]:
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        lookup: dict[str, list[SystemsEntryRecord]] = defaultdict(list)
        for source_id in enabled_source_ids:
            for entry in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="optionalfeature",
                limit=None,
            ):
                lookup[normalize_lookup(entry.title)].append(entry)
        return dict(lookup)

    def _build_optionalfeature_feature_type_lookup(
        self,
        campaign_slug: str,
    ) -> dict[str, list[SystemsEntryRecord]]:
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        lookup: dict[str, list[SystemsEntryRecord]] = defaultdict(list)
        for source_id in enabled_source_ids:
            for entry in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="optionalfeature",
                limit=None,
            ):
                for feature_type in self._normalize_optionalfeature_type_codes(entry.metadata.get("feature_type")):
                    lookup[feature_type].append(entry)
        for feature_type, entries in lookup.items():
            lookup[feature_type] = sorted(
                entries,
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
        return dict(lookup)

    def _build_feature_progression_groups(
        self,
        campaign_slug: str,
        *,
        matching_entries: list[SystemsEntryRecord],
        progression_rows: object,
    ) -> list[dict[str, object]]:
        if not matching_entries:
            return []
        if not isinstance(progression_rows, list):
            return []

        optionalfeature_lookup = self._build_optionalfeature_entry_lookup(campaign_slug)
        grouped_entries: dict[int, list[SystemsEntryRecord]] = defaultdict(list)
        for candidate in matching_entries:
            grouped_entries[self._coerce_int(candidate.metadata.get("level"), default=0)].append(candidate)

        rows: list[dict[str, object]] = []
        rendered_levels: set[int] = set()
        for group in progression_rows:
            if not isinstance(group, dict):
                continue
            level_label = str(group.get("name", "") or "").strip()
            level = self._extract_level_from_progression_label(level_label)
            if level > 0:
                rendered_levels.add(level)
            entries_for_level = sorted(
                grouped_entries.get(level, []),
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
            unmatched_entries = list(entries_for_level)
            feature_rows: list[dict[str, object]] = []
            raw_labels = group.get("entries")
            if isinstance(raw_labels, list):
                for raw_label in raw_labels:
                    label = str(raw_label or "").strip()
                    if not label:
                        continue
                    matched_entry = self._pop_matching_class_feature_entry(unmatched_entries, label)
                    feature_rows.append(
                        {
                            "label": label,
                            "entry": matched_entry,
                            "embedded_card": self._build_embedded_feature_card(
                                campaign_slug,
                                matched_entry,
                                optionalfeature_lookup=optionalfeature_lookup,
                            )
                            if matched_entry is not None
                            else None,
                        }
                    )
            for extra_entry in unmatched_entries:
                feature_rows.append(
                    {
                        "label": extra_entry.title,
                        "entry": extra_entry,
                        "embedded_card": self._build_embedded_feature_card(
                            campaign_slug,
                            extra_entry,
                            optionalfeature_lookup=optionalfeature_lookup,
                        ),
                    }
                )
            if not feature_rows:
                continue
            rows.append({"level": level, "level_label": level_label or f"Level {level}", "feature_rows": feature_rows})
        for level in sorted(level_key for level_key in grouped_entries if level_key > 0 and level_key not in rendered_levels):
            extra_entries = sorted(
                grouped_entries.get(level, []),
                key=lambda item: (
                    item.title.lower(),
                    item.source_id,
                    item.id,
                ),
            )
            if not extra_entries:
                continue
            rows.append(
                {
                    "level": level,
                    "level_label": f"Level {level}",
                    "feature_rows": [
                        {
                            "label": extra_entry.title,
                            "entry": extra_entry,
                            "embedded_card": self._build_embedded_feature_card(
                                campaign_slug,
                                extra_entry,
                                optionalfeature_lookup=optionalfeature_lookup,
                            ),
                        }
                        for extra_entry in extra_entries
                    ],
                }
            )
        return rows

    def _build_embedded_feature_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
        page_ref = str(entry.metadata.get("page_ref") or "").strip()
        if page_ref:
            return {
                "meta_badges": self._build_embedded_feature_badges(entry),
                "body_html": self._build_campaign_page_body_html(campaign_slug, page_ref),
                "option_groups": [],
            }
        body_html, option_groups = self._render_embedded_content(
            campaign_slug,
            entry.body.get("entries"),
            heading_level=5,
            extract_option_groups=True,
            optionalfeature_lookup=optionalfeature_lookup,
            preferred_source_id=entry.source_id,
        )
        return {
            "meta_badges": self._build_embedded_feature_badges(entry),
            "body_html": body_html,
            "option_groups": option_groups,
        }

    def _build_embedded_feature_badges(self, entry: SystemsEntryRecord) -> list[str]:
        entry_type_labels = {
            "classfeature": "Class Feature",
            "optionalfeature": "Optional Feature",
            "subclassfeature": "Subclass Feature",
        }
        badges: list[str] = []
        entry_type_label = entry_type_labels.get(entry.entry_type)
        if entry_type_label:
            badges.append(entry_type_label)

        class_name = str(entry.metadata.get("class_name", "") or "").strip()
        if class_name:
            badges.append(class_name)

        subclass_name = str(entry.metadata.get("subclass_name", "") or "").strip()
        if subclass_name:
            badges.append(subclass_name)

        if entry.source_id:
            badges.append(entry.source_id)

        level = self._coerce_int(entry.metadata.get("level"), default=0)
        if level > 0:
            badges.append(f"Level {level}")
        return badges

    def _campaign_progression_entries_for_class_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        return [
            candidate
            for candidate in self._list_campaign_progression_entries(campaign_slug)
            if candidate.entry_type == "classfeature"
            and self._campaign_progression_entry_matches_class(entry, candidate)
        ]

    def _campaign_progression_entries_for_subclass_entry(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
    ) -> list[SystemsEntryRecord]:
        return [
            candidate
            for candidate in self._list_campaign_progression_entries(campaign_slug)
            if candidate.entry_type == "subclassfeature"
            and self._campaign_progression_entry_matches_subclass(entry, candidate)
        ]

    def _list_campaign_progression_entries(self, campaign_slug: str) -> list[SystemsEntryRecord]:
        campaign = self._get_campaign(campaign_slug)
        page_store = getattr(self.repository_store, "page_store", None)
        if campaign is None or page_store is None:
            return []
        records = page_store.list_page_records(
            campaign_slug,
            content_dir=Path(campaign.player_content_dir),
            include_body=True,
        )
        entries: list[SystemsEntryRecord] = []
        seen_keys: set[str] = set()
        for record in records:
            page = getattr(record, "page", None)
            if page is None or not campaign.is_page_visible(page):
                continue
            if str(getattr(page, "section", "") or "").strip() != "Mechanics":
                continue
            for entry in build_campaign_page_progression_entries(record):
                entry_key = str(entry.entry_key or "").strip()
                if entry_key and entry_key in seen_keys:
                    continue
                if entry_key:
                    seen_keys.add(entry_key)
                entries.append(entry)
        return entries

    def _campaign_progression_entry_matches_class(
        self,
        class_entry: SystemsEntryRecord,
        progression_entry: SystemsEntryRecord,
    ) -> bool:
        class_name = str(progression_entry.metadata.get("class_name", "") or "").strip()
        if class_name != class_entry.title:
            return False
        class_source = str(progression_entry.metadata.get("class_source", "") or "").strip().upper()
        return not class_source or class_source == str(class_entry.source_id or "").strip().upper()

    def _campaign_progression_entry_matches_subclass(
        self,
        subclass_entry: SystemsEntryRecord,
        progression_entry: SystemsEntryRecord,
    ) -> bool:
        if not self._campaign_progression_entry_matches_class_name_only(subclass_entry, progression_entry):
            return False
        subclass_name = str(progression_entry.metadata.get("subclass_name", "") or "").strip()
        if subclass_name:
            subclass_title_variants = self._build_optionalfeature_title_variants(subclass_entry.title)
            feature_title_variants = self._build_optionalfeature_title_variants(subclass_name)
            if not (
                self._optionalfeature_titles_exactly_match(subclass_title_variants, feature_title_variants)
                or self._optionalfeature_titles_loosely_match(subclass_title_variants, feature_title_variants)
            ):
                return False
        subclass_source = str(progression_entry.metadata.get("subclass_source", "") or "").strip().upper()
        return not subclass_source or subclass_source == str(subclass_entry.source_id or "").strip().upper()

    def _campaign_progression_entry_matches_class_name_only(
        self,
        subclass_entry: SystemsEntryRecord,
        progression_entry: SystemsEntryRecord,
    ) -> bool:
        class_name = str(progression_entry.metadata.get("class_name", "") or "").strip()
        if class_name != str(subclass_entry.metadata.get("class_name", "") or "").strip():
            return False
        class_source = str(progression_entry.metadata.get("class_source", "") or "").strip().upper()
        subclass_class_source = str(subclass_entry.metadata.get("class_source", "") or "").strip().upper()
        return not class_source or class_source == subclass_class_source

    def _build_campaign_page_body_html(self, campaign_slug: str, page_ref: str) -> str:
        repository = self.repository_store.get()
        return str(repository.get_page_body_html(campaign_slug, page_ref) or "").strip()

    def _render_character_sheet_progression_groups(self, groups: list[dict[str, object]]) -> str:
        list_items: list[str] = []
        for group in groups:
            level_label = str(group.get("level_label") or "").strip()
            feature_rows = group.get("feature_rows")
            if not isinstance(feature_rows, list):
                continue
            labels = [
                str(row.get("label") or "").strip()
                for row in feature_rows
                if isinstance(row, dict) and str(row.get("label") or "").strip()
            ]
            if not labels:
                continue
            joined_labels = ", ".join(labels)
            if level_label:
                list_items.append(
                    f"<li><strong>{escape(level_label)}:</strong> {escape(joined_labels)}</li>"
                )
            else:
                list_items.append(f"<li>{escape(joined_labels)}</li>")
        if not list_items:
            return ""
        return "<p>Feature progression:</p><ul>" + "".join(list_items) + "</ul>"

    def _strip_systems_entry_summary_section(self, rendered_html: str) -> str:
        html = str(rendered_html or "").strip()
        if not html:
            return ""
        return re.sub(
            r"^\s*<section class=\"systems-entry-summary\">.*?</section>\s*",
            "",
            html,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

    def _build_embedded_optionalfeature_option(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
        return {
            "label": entry.title,
            "slug": entry.slug,
            "meta_badges": self._build_embedded_feature_badges(entry),
            "body_html": self._render_embedded_content(
                campaign_slug,
                entry.body.get("entries"),
                heading_level=6,
                extract_option_groups=False,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=entry.source_id,
            )[0],
        }

    def _build_embedded_option_group(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> dict[str, object]:
        count = self._coerce_int(value.get("count"), default=1)
        options: list[dict[str, object]] = []
        raw_entries = value.get("entries")
        if isinstance(raw_entries, list):
            for raw_option in raw_entries:
                resolved_entry = self._resolve_optionalfeature_entry(
                    raw_option,
                    optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
                label = self._format_feature_reference(raw_option)
                if resolved_entry is None:
                    if not label:
                        label = self._clean_embedded_text(str(raw_option or ""))
                    options.append(
                        {
                            "label": label,
                            "slug": None,
                            "meta_badges": [],
                            "body_html": "",
                        }
                    )
                    continue
                options.append(
                    self._build_embedded_optionalfeature_option(
                        campaign_slug,
                        resolved_entry,
                        optionalfeature_lookup=optionalfeature_lookup,
                    )
                )

        return {
            "summary_label": f"Choose {count} option{'s' if count != 1 else ''}",
            "options": options,
        }

    def _build_class_optionalfeature_section(
        self,
        campaign_slug: str,
        raw_section: object,
        *,
        feature_type_lookup: dict[str, list[SystemsEntryRecord]],
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object] | None:
        if not isinstance(raw_section, dict):
            return None
        title = self._clean_embedded_text(str(raw_section.get("name", "") or "")) or "Optional Features"
        feature_types = self._normalize_optionalfeature_type_codes(raw_section.get("featureType"))
        if not feature_types:
            return None

        options: list[dict[str, object]] = []
        seen_entry_keys: set[str] = set()
        for feature_type in feature_types:
            for entry in feature_type_lookup.get(feature_type, []):
                if entry.entry_key in seen_entry_keys:
                    continue
                seen_entry_keys.add(entry.entry_key)
                options.append(
                    self._build_embedded_optionalfeature_option(
                        campaign_slug,
                        entry,
                        optionalfeature_lookup=optionalfeature_lookup,
                    )
                )
        if not options:
            return None

        return {
            "title": title,
            "progression_text": self._format_optionalfeature_progression_text(raw_section.get("progression")),
            "options": options,
        }

    def _attach_optionalfeature_section_to_matching_class_feature(
        self,
        section: dict[str, object],
        class_feature_progression_groups: list[dict[str, object]],
    ) -> bool:
        section_title = normalize_lookup(str(section.get("title", "") or ""))
        section_title_variants = self._build_optionalfeature_title_variants(section_title)
        section_option_labels = self._collect_optionalfeature_section_option_labels(section)

        exact_matches: list[dict[str, object]] = []
        loose_matches: list[dict[str, object]] = []
        label_matches: list[dict[str, object]] = []
        for group in class_feature_progression_groups:
            if not isinstance(group, dict):
                continue
            feature_rows = group.get("feature_rows")
            if not isinstance(feature_rows, list):
                continue
            for row in feature_rows:
                if not isinstance(row, dict):
                    continue
                entry = row.get("entry")
                if not isinstance(entry, SystemsEntryRecord):
                    continue
                candidate_title = normalize_lookup(entry.title)
                candidate_title_variants = self._build_optionalfeature_title_variants(candidate_title)
                if self._optionalfeature_titles_exactly_match(section_title_variants, candidate_title_variants):
                    exact_matches.append(row)
                elif self._optionalfeature_titles_loosely_match(section_title_variants, candidate_title_variants):
                    loose_matches.append(row)
                if section_option_labels:
                    row_option_labels = self._collect_feature_row_optionalfeature_labels(row)
                    if (
                        row_option_labels
                        and (
                            row_option_labels == section_option_labels
                            or row_option_labels.issubset(section_option_labels)
                            or section_option_labels.issubset(row_option_labels)
                        )
                    ):
                        label_matches.append(row)

        if any(self._feature_row_already_surfaces_optionalfeatures(row) for row in label_matches):
            return True

        candidates = exact_matches or label_matches or loose_matches
        if not candidates:
            return False
        if any(self._feature_row_already_surfaces_optionalfeatures(row) for row in candidates):
            return True

        target_row = candidates[0]
        sections = target_row.setdefault("optionalfeature_sections", [])
        if isinstance(sections, list):
            sections.append(section)
        else:
            target_row["optionalfeature_sections"] = [section]
        return True

    def _feature_row_already_surfaces_optionalfeatures(self, row: dict[str, object]) -> bool:
        embedded_card = row.get("embedded_card")
        if isinstance(embedded_card, dict) and embedded_card.get("option_groups"):
            return True
        existing_sections = row.get("optionalfeature_sections")
        return isinstance(existing_sections, list) and bool(existing_sections)

    def _build_optionalfeature_title_variants(self, value: str) -> set[str]:
        normalized = normalize_lookup(value)
        if not normalized:
            return set()
        variants = {normalized}
        if normalized.endswith("s") and len(normalized) > 3:
            variants.add(normalized[:-1])
        return variants

    def _optionalfeature_titles_exactly_match(
        self,
        left_variants: set[str],
        right_variants: set[str],
    ) -> bool:
        return bool(left_variants and right_variants and (left_variants & right_variants))

    def _optionalfeature_titles_loosely_match(
        self,
        left_variants: set[str],
        right_variants: set[str],
    ) -> bool:
        if not left_variants or not right_variants:
            return False
        for left_value in left_variants:
            for right_value in right_variants:
                if left_value in right_value or right_value in left_value:
                    return True
        return False

    def _collect_optionalfeature_section_option_labels(self, section: dict[str, object]) -> set[str]:
        options = section.get("options")
        if not isinstance(options, list):
            return set()
        labels = {
            normalize_lookup(str(option.get("label", "") or ""))
            for option in options
            if isinstance(option, dict)
        }
        return {label for label in labels if label}

    def _collect_feature_row_optionalfeature_labels(self, row: dict[str, object]) -> set[str]:
        labels: set[str] = set()
        embedded_card = row.get("embedded_card")
        if isinstance(embedded_card, dict):
            option_groups = embedded_card.get("option_groups")
            if isinstance(option_groups, list):
                for option_group in option_groups:
                    if not isinstance(option_group, dict):
                        continue
                    options = option_group.get("options")
                    if not isinstance(options, list):
                        continue
                    for option in options:
                        if not isinstance(option, dict):
                            continue
                        label = normalize_lookup(str(option.get("label", "") or ""))
                        if label:
                            labels.add(label)
        existing_sections = row.get("optionalfeature_sections")
        if isinstance(existing_sections, list):
            for section in existing_sections:
                if not isinstance(section, dict):
                    continue
                labels.update(self._collect_optionalfeature_section_option_labels(section))
        return labels

    def _normalize_optionalfeature_type_codes(self, value: object) -> list[str]:
        if isinstance(value, list):
            codes = [str(item or "").strip().upper() for item in value]
        elif value is None:
            codes = []
        else:
            code = str(value or "").strip().upper()
            codes = [code] if code else []
        return [code for code in codes if code]

    def _format_optionalfeature_progression_text(self, value: object) -> str:
        if isinstance(value, dict):
            parts = []
            for raw_level, raw_count in sorted(
                value.items(),
                key=lambda item: self._coerce_int(item[0], default=0),
            ):
                level = self._coerce_int(raw_level, default=0)
                count = self._coerce_int(raw_count, default=0)
                if level <= 0 or count <= 0:
                    continue
                parts.append(f"Level {level}: {count}")
            return ", ".join(parts)
        if isinstance(value, list):
            parts = []
            last_count: int | None = None
            for index, raw_count in enumerate(value, start=1):
                count = self._coerce_int(raw_count, default=0)
                if count <= 0 or count == last_count:
                    last_count = count
                    continue
                parts.append(f"Level {index}: {count}")
                last_count = count
            return ", ".join(parts)
        return ""

    def _render_embedded_content(
        self,
        campaign_slug: str,
        value: object,
        *,
        heading_level: int,
        extract_option_groups: bool,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        if value is None:
            return "", []
        if isinstance(value, str):
            text = self._clean_embedded_text(value)
            return (f"<p>{escape(text)}</p>" if text else ""), []
        if isinstance(value, (int, float)):
            return f"<p>{escape(str(value))}</p>", []
        if isinstance(value, list):
            html_parts: list[str] = []
            option_groups: list[dict[str, object]] = []
            for item in value:
                rendered_html, nested_option_groups = self._render_embedded_content(
                    campaign_slug,
                    item,
                    heading_level=heading_level,
                    extract_option_groups=extract_option_groups,
                    optionalfeature_lookup=optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
                if rendered_html:
                    html_parts.append(rendered_html)
                option_groups.extend(nested_option_groups)
            return "\n".join(html_parts), option_groups
        if isinstance(value, dict):
            value_type = str(value.get("type", "") or "").strip().lower()
            if self._looks_like_ability_block(value):
                return self._render_embedded_ability_scores(value), []
            if value_type == "list":
                items = value.get("items")
                if not isinstance(items, list):
                    return "", []
                list_items: list[str] = []
                option_groups: list[dict[str, object]] = []
                for item in items:
                    rendered_item, nested_option_groups = self._render_embedded_list_item(
                        campaign_slug,
                        item,
                        heading_level=heading_level,
                        extract_option_groups=extract_option_groups,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    )
                    if rendered_item:
                        list_items.append(rendered_item)
                    option_groups.extend(nested_option_groups)
                if not list_items:
                    return "", option_groups
                return "<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>", option_groups
            if value_type == "options":
                if extract_option_groups:
                    option_group = self._build_embedded_option_group(
                        campaign_slug,
                        value,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    )
                    return "", ([option_group] if option_group["options"] else [])
                return self._render_embedded_option_list(
                    campaign_slug,
                    value,
                    heading_level=heading_level,
                    optionalfeature_lookup=optionalfeature_lookup,
                    preferred_source_id=preferred_source_id,
                )
            if value_type == "table":
                return self._render_embedded_table(value), []
            if value_type in {"abilitydc", "abilityattackmod"}:
                return self._render_embedded_ability_formula(value), []
            if value_type in {"refclassfeature", "refoptionalfeature", "refsubclassfeature"}:
                return (
                    self._render_embedded_reference(
                        campaign_slug,
                        value,
                        optionalfeature_lookup=optionalfeature_lookup,
                        preferred_source_id=preferred_source_id,
                    ),
                    [],
                )

            name = self._clean_embedded_text(str(value.get("name", "") or ""))
            entries = value.get("entries")
            entry_value = entries if entries is not None else value.get("entry")
            rendered_entries, option_groups = self._render_embedded_content(
                campaign_slug,
                entry_value,
                heading_level=min(heading_level + 1, 6),
                extract_option_groups=extract_option_groups,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if name and rendered_entries:
                heading_tag = f"h{heading_level}"
                return f"<section><{heading_tag}>{escape(name)}</{heading_tag}>{rendered_entries}</section>", option_groups
            if name:
                return f"<p><strong>{escape(name)}.</strong></p>", option_groups
            return rendered_entries, option_groups
        text = self._clean_embedded_text(str(value or ""))
        return (f"<p>{escape(text)}</p>" if text else ""), []

    def _render_embedded_list_item(
        self,
        campaign_slug: str,
        item: object,
        *,
        heading_level: int,
        extract_option_groups: bool,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        if isinstance(item, dict) and str(item.get("type", "") or "").strip().lower() == "item":
            name = self._clean_embedded_text(str(item.get("name", "") or ""))
            entry_value = item.get("entry", item.get("entries"))
            entry_text, option_groups = self._render_embedded_content(
                campaign_slug,
                entry_value,
                heading_level=heading_level,
                extract_option_groups=extract_option_groups,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            stripped_entry_text = self._strip_outer_paragraph(entry_text)
            if name and stripped_entry_text:
                return f"<strong>{escape(name)}</strong> {stripped_entry_text}", option_groups
            if name:
                return f"<strong>{escape(name)}</strong>", option_groups
            return stripped_entry_text, option_groups
        rendered_html, option_groups = self._render_embedded_content(
            campaign_slug,
            item,
            heading_level=heading_level,
            extract_option_groups=extract_option_groups,
            optionalfeature_lookup=optionalfeature_lookup,
            preferred_source_id=preferred_source_id,
        )
        return self._strip_outer_paragraph(rendered_html), option_groups

    def _render_embedded_option_list(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        heading_level: int,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> tuple[str, list[dict[str, object]]]:
        parts: list[str] = []
        count = value.get("count")
        if count not in (None, ""):
            count_text = str(count).strip()
            if count_text:
                parts.append(f"<p>Choose {escape(count_text)} option{'s' if count_text != '1' else ''}:</p>")
        option_entries = value.get("entries")
        if not isinstance(option_entries, list):
            return "".join(parts), []
        list_items: list[str] = []
        for item in option_entries:
            rendered_item, _ = self._render_embedded_list_item(
                campaign_slug,
                item,
                heading_level=heading_level,
                extract_option_groups=False,
                optionalfeature_lookup=optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if rendered_item:
                list_items.append(rendered_item)
        if list_items:
            parts.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
        return "".join(parts), []

    def _render_embedded_table(self, value: dict[str, object]) -> str:
        rows = value.get("rows")
        if not isinstance(rows, list):
            return ""
        parts = ['<div class="table-scroll"><table>']
        caption = self._clean_embedded_text(str(value.get("caption", "") or ""))
        if caption:
            parts.append(f"<caption>{escape(caption)}</caption>")
        headers = value.get("colLabels")
        if isinstance(headers, list) and headers:
            parts.append("<thead><tr>")
            for header in headers:
                header_text = self._clean_embedded_text(str(header or ""))
                parts.append(f"<th>{escape(header_text)}</th>")
            parts.append("</tr></thead>")
        parts.append("<tbody>")
        for row in rows:
            if not isinstance(row, list):
                continue
            parts.append("<tr>")
            for cell in row:
                cell_text = self._clean_embedded_text(str(cell or ""))
                parts.append(f"<td>{escape(cell_text)}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table></div>")
        return "".join(parts)

    def _render_embedded_ability_scores(self, value: dict[str, object]) -> str:
        headers: list[str] = []
        cells: list[str] = []
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            score = value.get(ability)
            if score is None:
                continue
            headers.append(f"<th>{escape(ability.upper())}</th>")
            cells.append(f"<td>{escape(str(score))}</td>")
        if not headers:
            return ""
        return (
            '<div class="table-scroll"><table>'
            + "<thead><tr>"
            + "".join(headers)
            + "</tr></thead><tbody><tr>"
            + "".join(cells)
            + "</tr></tbody></table></div>"
        )

    def _render_embedded_ability_formula(self, value: dict[str, object]) -> str:
        value_type = str(value.get("type", "") or "").strip().lower()
        name = self._clean_embedded_text(str(value.get("name", "") or "")) or "Spell"
        ability_phrase = self._format_embedded_ability_attribute_phrase(value.get("attributes"))
        if value_type == "abilitydc":
            formula = (
                f"8 + your proficiency bonus + your {ability_phrase} modifier"
                if ability_phrase
                else "8 + your proficiency bonus + your spellcasting ability modifier"
            )
            return f"<p><strong>{escape(name)} save DC:</strong> {escape(formula)}</p>"
        if value_type == "abilityattackmod":
            formula = (
                f"your proficiency bonus + your {ability_phrase} modifier"
                if ability_phrase
                else "your proficiency bonus + your spellcasting ability modifier"
            )
            return f"<p><strong>{escape(name)} attack modifier:</strong> {escape(formula)}</p>"
        return ""

    def _format_embedded_ability_attribute_phrase(self, value: object) -> str:
        if isinstance(value, list):
            labels = [
                ABILITY_NAME_LABELS.get(str(item or "").strip().lower(), str(item or "").strip())
                for item in value
                if str(item or "").strip()
            ]
        elif value is None:
            labels = []
        else:
            raw_value = str(value or "").strip()
            labels = [ABILITY_NAME_LABELS.get(raw_value.lower(), raw_value)] if raw_value else []
        if not labels:
            return ""
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} or {labels[1]}"
        return ", ".join(labels[:-1]) + f", or {labels[-1]}"

    def _render_embedded_reference(
        self,
        campaign_slug: str,
        value: dict[str, object],
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        preferred_source_id: str,
    ) -> str:
        label = self._format_feature_reference(value)
        if not label:
            return ""
        value_type = str(value.get("type", "") or "").strip().lower()
        if value_type == "refoptionalfeature":
            resolved_entry = self._resolve_optionalfeature_entry(
                value,
                optionalfeature_lookup,
                preferred_source_id=preferred_source_id,
            )
            if resolved_entry is not None:
                href = self._build_entry_href(campaign_slug, resolved_entry.slug)
                return f'<p><a href="{escape(href)}">{escape(resolved_entry.title)}</a></p>'
        return f"<p>{escape(label)}</p>"

    def _build_entry_href(self, campaign_slug: str, entry_slug: str) -> str:
        return f"/campaigns/{campaign_slug}/systems/entries/{entry_slug}"

    def _resolve_optionalfeature_entry(
        self,
        value: object,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
        *,
        preferred_source_id: str,
    ) -> SystemsEntryRecord | None:
        label, source_id = self._split_optionalfeature_reference(value)
        if not label:
            return None
        candidates = optionalfeature_lookup.get(normalize_lookup(label), [])
        if not candidates:
            return None
        if source_id:
            for candidate in candidates:
                if candidate.source_id.upper() == source_id:
                    return candidate
        for candidate in candidates:
            if candidate.source_id.upper() == preferred_source_id.upper():
                return candidate
        return candidates[0]

    def _split_optionalfeature_reference(self, value: object) -> tuple[str, str | None]:
        raw_reference = value
        if isinstance(value, dict):
            raw_reference = value.get("optionalfeature")
        if isinstance(raw_reference, str):
            parts = [part.strip() for part in raw_reference.split("|")]
            label = parts[0] if parts else ""
            source_id = parts[1].upper() if len(parts) > 1 and parts[1] else None
            return label, source_id
        return self._format_feature_reference(value), None

    def _format_feature_reference(self, value: object) -> str:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split("|")]
            return self._clean_embedded_text(parts[0]) if parts else ""
        if isinstance(value, dict):
            raw_reference = (
                value.get("classFeature")
                or value.get("subclassFeature")
                or value.get("optionalfeature")
            )
            label = self._format_feature_reference(raw_reference)
            if value.get("gainSubclassFeature") and label:
                return f"{label} (choose subclass feature)"
            return label
        return self._clean_embedded_text(str(value or ""))

    def _clean_embedded_text(self, value: str) -> str:
        stripped = self._strip_embedded_inline_tags(value)
        return re.sub(r"\s+", " ", stripped).strip()

    def _strip_embedded_inline_tags(self, value: str) -> str:
        rendered = str(value or "")
        while True:
            updated = INLINE_TAG_PATTERN.sub(self._replace_embedded_inline_tag, rendered)
            if updated == rendered:
                return updated
            rendered = updated

    def _replace_embedded_inline_tag(self, match: re.Match[str]) -> str:
        body = match.group(1).strip()
        tag, _, remainder = body.partition(" ")
        normalized_tag = tag.lower()
        raw_text = remainder.strip()
        primary_text = raw_text.split("|", 1)[0].strip()
        if normalized_tag == "atk":
            return ATTACK_TAG_LABELS.get(raw_text.lower(), primary_text or raw_text)
        if normalized_tag == "hit":
            if not primary_text:
                return ""
            if primary_text.startswith(("+", "-")):
                return primary_text
            return f"+{primary_text}"
        if normalized_tag == "h":
            return "Hit:"
        if normalized_tag == "dc":
            return f"DC {primary_text}"
        if normalized_tag in {"damage", "dice", "chance", "recharge", "skill", "condition", "status", "disease"}:
            return primary_text
        if normalized_tag in {
            "action",
            "background",
            "book",
            "class",
            "classfeature",
            "creature",
            "deity",
            "feat",
            "filter",
            "item",
            "language",
            "object",
            "optfeature",
            "race",
            "sense",
            "spell",
            "table",
            "trap",
            "variantrule",
            "vehicle",
        }:
            return primary_text
        return primary_text or raw_text or normalized_tag

    def _build_class_proficiency_blocks(
        self,
        value: object,
        *,
        skill_lookup: dict[str, SystemsEntryRecord] | None = None,
    ) -> list[dict[str, object]]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            return [{"kind": "text", "text": value}]
        if isinstance(value, list):
            if not value:
                return []
            if all(not isinstance(item, (dict, list)) for item in value):
                rendered = ", ".join(part for part in (str(item).strip() for item in value) if part)
                return [{"kind": "text", "text": rendered}] if rendered else []

            blocks: list[dict[str, object]] = []
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("choose"), dict):
                    choose = item.get("choose") or {}
                    raw_options = choose.get("from")
                    options: list[dict[str, str | None]] = []
                    if isinstance(raw_options, list):
                        for raw_option in raw_options:
                            label = self._humanize_skill_or_term(raw_option)
                            normalized = normalize_lookup(label)
                            linked_entry = skill_lookup.get(normalized) if skill_lookup else None
                            options.append(
                                {
                                    "label": linked_entry.title if linked_entry is not None else label,
                                    "slug": linked_entry.slug if linked_entry is not None else None,
                                }
                            )
                    blocks.append(
                        {
                            "kind": "choice",
                            "count": self._coerce_int(choose.get("count"), default=1),
                            "options": options,
                        }
                    )
                    continue
                rendered = self._format_proficiency_block_text(item)
                if rendered:
                    blocks.append({"kind": "text", "text": rendered})
            return blocks
        rendered = self._format_proficiency_block_text(value)
        return [{"kind": "text", "text": rendered}] if rendered else []

    def _format_proficiency_block_text(self, value: object) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return ", ".join(
                part for part in (self._format_proficiency_block_text(item) for item in value) if part
            )
        if isinstance(value, dict):
            parts: list[str] = []
            for key, nested_value in value.items():
                rendered = self._format_proficiency_block_text(nested_value)
                if not rendered:
                    continue
                parts.append(f"{str(key).replace('_', ' ').title()}: {rendered}")
            return "; ".join(parts)
        return str(value).strip()

    def _humanize_skill_or_term(self, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return " ".join(part.capitalize() for part in text.split())

    def _extract_level_from_progression_label(self, value: str) -> int:
        match = re.search(r"(\d+)", str(value or ""))
        if match is None:
            return 0
        return self._coerce_int(match.group(1), default=0)

    def _normalize_class_feature_progression_label(self, value: str) -> str:
        cleaned = str(value or "").replace(" (choose subclass feature)", "").strip()
        return normalize_lookup(cleaned)

    def _pop_matching_class_feature_entry(
        self,
        candidates: list[SystemsEntryRecord],
        label: str,
    ) -> SystemsEntryRecord | None:
        normalized_label = self._normalize_class_feature_progression_label(label)
        for index, candidate in enumerate(candidates):
            if normalize_lookup(candidate.title) == normalized_label:
                return candidates.pop(index)
        return None

    def _looks_like_ability_block(self, value: dict[str, object]) -> bool:
        return any(key in value for key in ("str", "dex", "con", "int", "wis", "cha"))

    def _strip_outer_paragraph(self, html: str) -> str:
        cleaned = html.strip()
        if cleaned.startswith("<p>") and cleaned.endswith("</p>"):
            return cleaned[3:-4].strip()
        return cleaned

    def _coerce_int(self, value: object, *, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _extract_monster_hp_average(self, value: object) -> int:
        if isinstance(value, dict):
            return self._coerce_int(value.get("average"), default=0)
        return self._coerce_int(value, default=0)

    def _extract_max_distance(self, value: object) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            distances = [int(match) for match in re.findall(r"\d+", value)]
            return max(distances) if distances else 0
        if isinstance(value, list):
            distances = [self._extract_max_distance(item) for item in value]
            return max(distances) if distances else 0
        if isinstance(value, dict):
            distances = [self._extract_max_distance(item) for item in value.values()]
            return max(distances) if distances else 0
        return 0

    def _format_speed_label(self, value: object) -> str:
        if isinstance(value, (int, float)):
            return f"{int(value)} ft."
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            parts: list[str] = []
            for movement_type in ("walk", "burrow", "climb", "fly", "swim"):
                if movement_type not in value:
                    continue
                movement_value = value[movement_type]
                if movement_value is True:
                    rendered_value = "equal to walking speed"
                else:
                    distance = self._extract_max_distance(movement_value)
                    rendered_value = f"{distance} ft." if distance else str(movement_value).strip()
                parts.append(f"{movement_type.title()} {rendered_value}".strip())
            return ", ".join(parts)
        return ""
