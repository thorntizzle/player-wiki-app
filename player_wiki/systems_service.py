from __future__ import annotations

from html import escape
import re
from collections import defaultdict
from dataclasses import dataclass

from .auth_store import isoformat, utcnow
from .campaign_visibility import (
    VISIBILITY_DM,
    VISIBILITY_PLAYERS,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    is_valid_visibility,
    normalize_visibility_choice,
)
from .repository import normalize_lookup
from .repository_store import RepositoryStore
from .systems_models import (
    CampaignSystemsPolicyRecord,
    SystemsEntryRecord,
    SystemsLibraryRecord,
    SystemsSourceRecord,
)
from .systems_store import SystemsStore

LICENSE_CLASS_LABELS = {
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
                is_enabled = bool(seed.get("enabled", False))
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
        return self.store.list_entries_for_campaign_source(
            campaign_slug,
            state.source.library_slug,
            state.source.source_id,
            entry_type=entry_type,
            query=query,
            limit=limit,
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
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        if not enabled_source_ids:
            return []

        matching_entries: list[SystemsEntryRecord] = []
        for source_id in enabled_source_ids:
            for candidate in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="classfeature",
                limit=None,
            ):
                if str(candidate.metadata.get("class_name", "") or "").strip() != entry.title:
                    continue
                if str(candidate.metadata.get("class_source", "") or "").strip().upper() != entry.source_id:
                    continue
                matching_entries.append(candidate)

        progression_rows = entry.body.get("feature_progression")
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
        enabled_source_ids = [
            row.source.source_id
            for row in self.list_campaign_source_states(campaign_slug)
            if row.is_enabled
        ]
        if not enabled_source_ids:
            return []

        class_name = str(entry.metadata.get("class_name", "") or "").strip()
        class_source = str(entry.metadata.get("class_source", "") or "").strip().upper()
        matching_entries: list[SystemsEntryRecord] = []
        for source_id in enabled_source_ids:
            for candidate in self.list_entries_for_campaign_source(
                campaign_slug,
                source_id,
                entry_type="subclassfeature",
                limit=None,
            ):
                if str(candidate.metadata.get("class_name", "") or "").strip() != class_name:
                    continue
                if str(candidate.metadata.get("class_source", "") or "").strip().upper() != class_source:
                    continue
                if not self._subclass_entry_matches_feature(entry, candidate):
                    continue
                if str(candidate.metadata.get("subclass_source", "") or "").strip().upper() != entry.source_id:
                    continue
                matching_entries.append(candidate)

        progression_rows = entry.body.get("feature_progression")
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
        for group in progression_rows:
            if not isinstance(group, dict):
                continue
            level_label = str(group.get("name", "") or "").strip()
            level = self._extract_level_from_progression_label(level_label)
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
        return rows

    def _build_embedded_feature_card(
        self,
        campaign_slug: str,
        entry: SystemsEntryRecord,
        *,
        optionalfeature_lookup: dict[str, list[SystemsEntryRecord]],
    ) -> dict[str, object]:
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
