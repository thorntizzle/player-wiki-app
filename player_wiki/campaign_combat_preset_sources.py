from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import yaml

from .campaign_combat_service import (
    build_character_combat_snapshot,
    normalize_npc_resource_counter_seeds,
    normalize_npc_resource_note_seeds,
)
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
    COMBAT_SOURCE_KINDS,
)
from .combat_npc_resources import (
    NpcResourceCounterSeed,
    NpcResourceNoteSeed,
    build_npc_resource_seeds_from_markdown,
    build_npc_resource_seeds_from_systems_entry,
)
from .combat_preset_models import (
    CampaignCombatPresetEntryInput,
    CampaignCombatPresetEntryRecord,
    CampaignCombatPresetMaterializedSeed,
    CampaignCombatPresetSourceInspection,
)
from .db import get_db
from .system_policy import default_systems_library_slug


COMBAT_SEED_VERSION_SCHEME = "combat-seed-v1-sha256"
MAX_PRESET_EXPANDED_QUANTITY = 50
_VERSION_PATTERN = re.compile(r"^[0-9a-f]{64}$")

SOURCE_STATUS_CURRENT = "current"
SOURCE_STATUS_CHANGED = "source_changed"
SOURCE_STATUS_MISSING = "missing_or_inaccessible"
SOURCE_STATUS_SOURCE_DISABLED = "source_disabled"
SOURCE_STATUS_ENTRY_DISABLED = "entry_disabled"


class CampaignCombatPresetSourceValidationError(ValueError):
    """A preset source row cannot be safely prepared or materialized."""


@dataclass(frozen=True, slots=True)
class _ResolvedCombatSeed:
    source_kind: str
    source_ref: str
    source_version: str
    display_name: str
    initiative_bonus: int
    dexterity_modifier: int
    current_hp: int
    max_hp: int
    temp_hp: int
    movement_total: int
    resource_counter_seeds: tuple[NpcResourceCounterSeed, ...] = ()
    resource_note_seeds: tuple[NpcResourceNoteSeed, ...] = ()


@dataclass(frozen=True, slots=True)
class _SourceResolution:
    status: str
    seed: _ResolvedCombatSeed | None = None


DMStatblockBatchLoader = Callable[[str, tuple[int, ...]], dict[str, object]]
SystemsCampaignConfigLoader = Callable[
    [str], tuple[str, dict[str, dict[str, object]]]
]


class CampaignCombatPresetSourceResolver:
    def __init__(
        self,
        character_repository,
        dm_content_service,
        systems_service,
        *,
        dm_statblock_batch_loader: DMStatblockBatchLoader | None = None,
        systems_campaign_config_loader: SystemsCampaignConfigLoader | None = None,
    ) -> None:
        self.character_repository = character_repository
        self.dm_content_service = dm_content_service
        self.systems_service = systems_service
        self._dm_statblock_batch_loader = (
            dm_statblock_batch_loader or self._load_dm_statblocks
        )
        self._systems_campaign_config_loader = (
            systems_campaign_config_loader or self._load_systems_campaign_config
        )

    def prepare_entries_for_save(
        self,
        campaign_slug: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> tuple[CampaignCombatPresetEntryInput, ...]:
        normalized = self._normalize_entries(entries, saved_versions=False)
        resolutions = self._resolve_unique_sources(campaign_slug, normalized)
        prepared: list[CampaignCombatPresetEntryInput] = []
        for entry in normalized:
            if entry.source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
                prepared.append(entry)
                continue
            resolution = resolutions[(entry.source_kind, entry.source_ref)]
            seed = self._require_available(resolution)
            prepared.append(
                replace(
                    entry,
                    source_version=seed.source_version,
                    version_scheme=COMBAT_SEED_VERSION_SCHEME,
                )
            )
        return tuple(prepared)

    def inspect_entries(
        self,
        campaign_slug: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> tuple[CampaignCombatPresetSourceInspection, ...]:
        normalized = self._normalize_entries(entries, saved_versions=True)
        resolutions = self._resolve_unique_sources(campaign_slug, normalized)
        rows: list[CampaignCombatPresetSourceInspection] = []
        for position, entry in enumerate(normalized):
            if entry.source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
                rows.append(
                    CampaignCombatPresetSourceInspection(
                        position=position,
                        source_kind=entry.source_kind,
                        status=SOURCE_STATUS_CURRENT,
                        display_name=entry.custom_name,
                    )
                )
                continue
            resolution = resolutions[(entry.source_kind, entry.source_ref)]
            status = resolution.status
            if (
                status == SOURCE_STATUS_CURRENT
                and resolution.seed is not None
                and entry.source_version != resolution.seed.source_version
            ):
                status = SOURCE_STATUS_CHANGED
            rows.append(
                CampaignCombatPresetSourceInspection(
                    position=position,
                    source_kind=entry.source_kind,
                    status=status,
                )
            )
        return tuple(rows)

    def resolve_entries_for_apply(
        self,
        campaign_slug: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> tuple[CampaignCombatPresetMaterializedSeed, ...]:
        normalized = self._normalize_entries(entries, saved_versions=True)
        resolutions = self._resolve_unique_sources(campaign_slug, normalized)
        materialized: list[CampaignCombatPresetMaterializedSeed] = []
        for position, entry in enumerate(normalized):
            if entry.source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
                seed = _ResolvedCombatSeed(
                    source_kind=entry.source_kind,
                    source_ref="",
                    source_version="",
                    display_name=entry.custom_name,
                    initiative_bonus=int(entry.initiative_bonus),
                    dexterity_modifier=int(entry.dexterity_modifier),
                    current_hp=int(entry.max_hp),
                    max_hp=int(entry.max_hp),
                    temp_hp=0,
                    movement_total=int(entry.movement_total),
                )
            else:
                resolution = resolutions[(entry.source_kind, entry.source_ref)]
                seed = self._require_available(resolution)
                if entry.source_version != seed.source_version:
                    raise CampaignCombatPresetSourceValidationError(
                        "A saved encounter preset source changed and must be reviewed and resaved."
                    )
            turn_value = (
                seed.initiative_bonus if entry.turn_value is None else entry.turn_value
            )
            for quantity_index in range(entry.quantity):
                materialized.append(
                    CampaignCombatPresetMaterializedSeed(
                        entry_id=entry.id,
                        position=position,
                        quantity_index=quantity_index,
                        source_kind=entry.source_kind,
                        source_ref=seed.source_ref,
                        source_version=(
                            seed.source_version
                            if entry.source_kind != COMBAT_SOURCE_KIND_MANUAL_NPC
                            else None
                        ),
                        version_scheme=(
                            COMBAT_SEED_VERSION_SCHEME
                            if entry.source_kind != COMBAT_SOURCE_KIND_MANUAL_NPC
                            else None
                        ),
                        display_name=seed.display_name,
                        turn_value=turn_value,
                        initiative_bonus=seed.initiative_bonus,
                        dexterity_modifier=seed.dexterity_modifier,
                        initiative_priority=entry.initiative_priority,
                        current_hp=seed.current_hp,
                        max_hp=seed.max_hp,
                        temp_hp=seed.temp_hp,
                        movement_total=seed.movement_total,
                        resource_counter_seeds=seed.resource_counter_seeds,
                        resource_note_seeds=seed.resource_note_seeds,
                    )
                )
        return tuple(materialized)

    def _normalize_entries(
        self,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
        *,
        saved_versions: bool,
    ) -> tuple[CampaignCombatPresetEntryInput, ...]:
        try:
            raw_entries = tuple(entries)
        except TypeError as exc:
            raise CampaignCombatPresetSourceValidationError(
                "Invalid encounter preset entries."
            ) from exc
        normalized: list[CampaignCombatPresetEntryInput] = []
        expanded_total = 0
        for raw_entry in raw_entries:
            entry = raw_entry.as_input() if isinstance(raw_entry, CampaignCombatPresetEntryRecord) else raw_entry
            if not isinstance(entry, CampaignCombatPresetEntryInput):
                raise CampaignCombatPresetSourceValidationError(
                    "Invalid encounter preset entry."
                )
            source_kind = self._exact_text(entry.source_kind, "source kind")
            if source_kind not in COMBAT_SOURCE_KINDS:
                raise CampaignCombatPresetSourceValidationError(
                    "Invalid encounter preset source kind."
                )
            quantity = self._bounded_int(entry.quantity, "quantity", minimum=1, maximum=50)
            expanded_total += quantity
            if expanded_total > MAX_PRESET_EXPANDED_QUANTITY:
                raise CampaignCombatPresetSourceValidationError(
                    "Encounter presets may expand to at most 50 combatants."
                )
            turn_value = (
                None
                if entry.turn_value is None or entry.turn_value == ""
                else self._bounded_int(entry.turn_value, "turn value")
            )
            initiative_priority = self._bounded_int(
                entry.initiative_priority,
                "initiative priority",
                minimum=1,
            )
            if source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
                normalized.append(
                    self._normalize_manual_entry(
                        entry,
                        quantity=quantity,
                        turn_value=turn_value,
                        initiative_priority=initiative_priority,
                    )
                )
                continue
            normalized.append(
                self._normalize_source_entry(
                    entry,
                    source_kind=source_kind,
                    quantity=quantity,
                    turn_value=turn_value,
                    initiative_priority=initiative_priority,
                    saved_versions=saved_versions,
                )
            )
        return tuple(normalized)

    def _normalize_manual_entry(
        self,
        entry: CampaignCombatPresetEntryInput,
        *,
        quantity: int,
        turn_value: int | None,
        initiative_priority: int,
    ) -> CampaignCombatPresetEntryInput:
        if entry.source_ref not in (None, "") or entry.source_version is not None or entry.version_scheme is not None:
            raise CampaignCombatPresetSourceValidationError(
                "Manual encounter preset entries cannot use source fields."
            )
        custom_name = str(entry.custom_name or "").strip()
        if not custom_name:
            raise CampaignCombatPresetSourceValidationError(
                "Manual encounter preset entries require a name."
            )
        initiative_bonus = self._bounded_int(entry.initiative_bonus, "initiative bonus")
        dexterity_modifier = self._bounded_int(entry.dexterity_modifier, "Dexterity modifier")
        max_hp = self._bounded_int(entry.max_hp, "max HP", minimum=0)
        movement_total = self._bounded_int(entry.movement_total, "movement", minimum=0)
        return replace(
            entry,
            source_kind=COMBAT_SOURCE_KIND_MANUAL_NPC,
            source_ref="",
            source_version=None,
            version_scheme=None,
            quantity=quantity,
            turn_value=turn_value,
            initiative_priority=initiative_priority,
            custom_name=custom_name,
            initiative_bonus=initiative_bonus,
            dexterity_modifier=dexterity_modifier,
            max_hp=max_hp,
            movement_total=movement_total,
        )

    def _normalize_source_entry(
        self,
        entry: CampaignCombatPresetEntryInput,
        *,
        source_kind: str,
        quantity: int,
        turn_value: int | None,
        initiative_priority: int,
        saved_versions: bool,
    ) -> CampaignCombatPresetEntryInput:
        source_ref = self._exact_text(entry.source_ref, "source reference")
        if not source_ref:
            raise CampaignCombatPresetSourceValidationError(
                "Invalid encounter preset source reference."
            )
        if source_kind == COMBAT_SOURCE_KIND_DM_STATBLOCK:
            if not source_ref.isdecimal() or str(int(source_ref)) != source_ref or int(source_ref) < 1:
                raise CampaignCombatPresetSourceValidationError(
                    "Invalid encounter preset source reference."
                )
        if (
            str(entry.custom_name or "")
            or entry.initiative_bonus is not None
            or entry.dexterity_modifier is not None
            or entry.max_hp is not None
            or entry.movement_total is not None
        ):
            raise CampaignCombatPresetSourceValidationError(
                "Source-backed encounter preset fields are derived from the source."
            )
        source_version = None
        version_scheme = None
        if saved_versions:
            if (
                entry.version_scheme != COMBAT_SEED_VERSION_SCHEME
                or not isinstance(entry.source_version, str)
                or _VERSION_PATTERN.fullmatch(entry.source_version) is None
            ):
                raise CampaignCombatPresetSourceValidationError(
                    "Invalid saved encounter preset source version."
                )
            source_version = entry.source_version
            version_scheme = entry.version_scheme
        return replace(
            entry,
            source_kind=source_kind,
            source_ref=source_ref,
            source_version=source_version,
            version_scheme=version_scheme,
            quantity=quantity,
            turn_value=turn_value,
            initiative_priority=initiative_priority,
            custom_name="",
            initiative_bonus=None,
            dexterity_modifier=None,
            max_hp=None,
            movement_total=None,
        )

    def _resolve_unique_sources(
        self,
        campaign_slug: str,
        entries: tuple[CampaignCombatPresetEntryInput, ...],
    ) -> dict[tuple[str, str], _SourceResolution]:
        refs_by_kind = {
            source_kind: tuple(
                sorted(
                    {
                        entry.source_ref
                        for entry in entries
                        if entry.source_kind == source_kind
                    }
                )
            )
            for source_kind in COMBAT_SOURCE_KINDS
            if source_kind != COMBAT_SOURCE_KIND_MANUAL_NPC
        }
        resolutions: dict[tuple[str, str], _SourceResolution] = {}
        self._resolve_characters(
            campaign_slug,
            refs_by_kind.get(COMBAT_SOURCE_KIND_CHARACTER, ()),
            resolutions,
        )
        self._resolve_dm_statblocks(
            campaign_slug,
            refs_by_kind.get(COMBAT_SOURCE_KIND_DM_STATBLOCK, ()),
            resolutions,
        )
        self._resolve_systems_monsters(
            campaign_slug,
            refs_by_kind.get(COMBAT_SOURCE_KIND_SYSTEMS_MONSTER, ()),
            resolutions,
        )
        return resolutions

    def _resolve_characters(self, campaign_slug, refs, resolutions) -> None:
        for source_ref in refs:
            try:
                record = self.character_repository.get_combat_seed_character(
                    campaign_slug,
                    source_ref,
                )
            except (OSError, TypeError, ValueError):
                record = None
            key = (COMBAT_SOURCE_KIND_CHARACTER, source_ref)
            if record is None:
                resolutions[key] = _SourceResolution(SOURCE_STATUS_MISSING)
                continue
            seed_fields = build_character_combat_snapshot(record)
            resolutions[key] = _SourceResolution(
                SOURCE_STATUS_CURRENT,
                self._build_resolved_seed(
                    source_kind=COMBAT_SOURCE_KIND_CHARACTER,
                    source_ref=source_ref,
                    display_name=str(seed_fields["display_name"]),
                    initiative_bonus=int(seed_fields["initiative_bonus"]),
                    dexterity_modifier=int(seed_fields["dexterity_modifier"]),
                    current_hp=int(seed_fields["current_hp"]),
                    max_hp=int(seed_fields["max_hp"]),
                    temp_hp=int(seed_fields["temp_hp"]),
                    movement_total=int(seed_fields["movement_total"]),
                ),
            )

    def _resolve_dm_statblocks(self, campaign_slug, refs, resolutions) -> None:
        if not refs:
            return
        ids = tuple(sorted(int(source_ref) for source_ref in refs))
        records = self._dm_statblock_batch_loader(campaign_slug, ids)
        for source_ref in refs:
            key = (COMBAT_SOURCE_KIND_DM_STATBLOCK, source_ref)
            statblock = records.get(source_ref)
            if statblock is None:
                resolutions[key] = _SourceResolution(SOURCE_STATUS_MISSING)
                continue
            counter_seeds, note_seeds = build_npc_resource_seeds_from_markdown(
                str(getattr(statblock, "body_markdown", "") or ""),
                source_label="DM Content",
            )
            resolutions[key] = _SourceResolution(
                SOURCE_STATUS_CURRENT,
                self._build_resolved_seed(
                    source_kind=COMBAT_SOURCE_KIND_DM_STATBLOCK,
                    source_ref=source_ref,
                    display_name=str(getattr(statblock, "title", "") or ""),
                    initiative_bonus=int(getattr(statblock, "initiative_bonus", 0) or 0),
                    dexterity_modifier=int(
                        self.dm_content_service.get_statblock_dexterity_modifier(statblock)
                    ),
                    max_hp=int(getattr(statblock, "max_hp", 0) or 0),
                    movement_total=int(getattr(statblock, "movement_total", 0) or 0),
                    resource_counter_seeds=counter_seeds,
                    resource_note_seeds=note_seeds,
                ),
            )

    def _resolve_systems_monsters(self, campaign_slug, refs, resolutions) -> None:
        if not refs:
            return
        library_slug, seed_by_id = self._systems_campaign_config_loader(campaign_slug)
        library = (
            self.systems_service.store.get_library(library_slug)
            if library_slug
            else None
        )
        if library is None:
            for source_ref in refs:
                resolutions[(COMBAT_SOURCE_KIND_SYSTEMS_MONSTER, source_ref)] = (
                    _SourceResolution(SOURCE_STATUS_MISSING)
                )
            return
        configured_by_id = {
            item.source_id: item
            for item in self.systems_service.store.list_campaign_enabled_sources(
                campaign_slug
            )
            if item.library_slug == library.library_slug
        }
        source_enabled_by_id: dict[str, bool] = {}
        for source in self.systems_service.store.list_sources(library.library_slug):
            source_id = str(source.source_id or "").strip()
            if not source_id:
                continue
            configured = configured_by_id.get(source_id)
            seed = seed_by_id.get(source_id, {})
            source_enabled_by_id[source_id] = (
                bool(configured.is_enabled)
                if configured is not None
                else (
                    bool(seed.get("enabled"))
                    if "enabled" in seed
                    else self.systems_service._default_enabled_for_source(source)
                )
            )
        entries = self.systems_service.store.list_entries_for_campaign_by_identity(
            campaign_slug,
            library.library_slug,
            list(source_enabled_by_id),
            entry_type="monster",
            entry_keys=list(refs),
        )
        entries_by_key = {entry.entry_key: entry for entry in entries}
        for source_ref in refs:
            key = (COMBAT_SOURCE_KIND_SYSTEMS_MONSTER, source_ref)
            entry = entries_by_key.get(source_ref)
            if entry is None:
                raw_entry = self.systems_service.store.get_entry(
                    library.library_slug,
                    source_ref,
                )
                if (
                    raw_entry is None
                    or raw_entry.entry_type != "monster"
                    or raw_entry.source_id not in source_enabled_by_id
                ):
                    resolutions[key] = _SourceResolution(SOURCE_STATUS_MISSING)
                    continue
                status = (
                    SOURCE_STATUS_SOURCE_DISABLED
                    if not source_enabled_by_id[raw_entry.source_id]
                    else SOURCE_STATUS_ENTRY_DISABLED
                )
                resolutions[key] = _SourceResolution(status)
                continue
            source_enabled = source_enabled_by_id.get(entry.source_id)
            if source_enabled is None:
                resolutions[key] = _SourceResolution(SOURCE_STATUS_MISSING)
                continue
            if not source_enabled:
                resolutions[key] = _SourceResolution(SOURCE_STATUS_SOURCE_DISABLED)
                continue
            monster_seed = self.systems_service.build_monster_combat_seed(entry)
            counter_seeds, note_seeds = build_npc_resource_seeds_from_systems_entry(
                entry,
                source_label=f"Systems {entry.source_id}",
            )
            resolutions[key] = _SourceResolution(
                SOURCE_STATUS_CURRENT,
                self._build_resolved_seed(
                    source_kind=COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
                    source_ref=source_ref,
                    display_name=monster_seed.title,
                    initiative_bonus=monster_seed.initiative_bonus,
                    dexterity_modifier=monster_seed.dexterity_modifier,
                    max_hp=monster_seed.max_hp,
                    movement_total=monster_seed.movement_total,
                    resource_counter_seeds=counter_seeds,
                    resource_note_seeds=note_seeds,
                    extra_projection={"source_id": monster_seed.source_id},
                ),
            )

    def _load_systems_campaign_config(
        self,
        campaign_slug: str,
    ) -> tuple[str, dict[str, dict[str, object]]]:
        try:
            campaigns_root = Path(self.character_repository.campaigns_dir).resolve()
            config_path = campaigns_root / campaign_slug / "campaign.yaml"
            resolved_config_path = config_path.resolve()
            if (
                campaigns_root not in resolved_config_path.parents
                or resolved_config_path != config_path
            ):
                return "", {}
            payload = yaml.safe_load(resolved_config_path.read_bytes().decode("utf-8")) or {}
        except (OSError, TypeError, ValueError, yaml.YAMLError, UnicodeError):
            return "", {}
        if (
            not isinstance(payload, dict)
            or str(payload.get("slug") or campaign_slug) != campaign_slug
        ):
            return "", {}
        library_slug = default_systems_library_slug(
            payload.get("systems_library") or payload.get("system")
        )
        seed_by_id: dict[str, dict[str, object]] = {}
        for item in list(payload.get("systems_sources") or []):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or "").strip()
            if source_id:
                seed_by_id[source_id] = dict(item)
        return library_slug, seed_by_id

    def _build_resolved_seed(
        self,
        *,
        source_kind: str,
        source_ref: str,
        display_name: str,
        initiative_bonus: int,
        dexterity_modifier: int,
        max_hp: int,
        movement_total: int,
        current_hp: int | None = None,
        temp_hp: int = 0,
        resource_counter_seeds=(),
        resource_note_seeds=(),
        extra_projection: dict[str, object] | None = None,
    ) -> _ResolvedCombatSeed:
        counters = normalize_npc_resource_counter_seeds(tuple(resource_counter_seeds))
        notes = normalize_npc_resource_note_seeds(tuple(resource_note_seeds))
        projection: dict[str, object] = {
            "source_ref": source_ref,
            "display_name": display_name,
            "initiative_bonus": int(initiative_bonus),
            "dexterity_modifier": int(dexterity_modifier),
            "max_hp": int(max_hp),
            "movement_total": int(movement_total),
        }
        if extra_projection:
            projection.update(extra_projection)
        if source_kind != COMBAT_SOURCE_KIND_CHARACTER:
            projection["resource_counter_seeds"] = [
                {
                    "resource_key": seed.resource_key,
                    "label": seed.label,
                    "current_value": seed.current_value,
                    "max_value": seed.max_value,
                    "reset_label": seed.reset_label,
                    "source_label": seed.source_label,
                }
                for seed in counters
            ]
            projection["resource_note_seeds"] = [
                {
                    "label": seed.label,
                    "note": seed.note,
                    "source_label": seed.source_label,
                }
                for seed in notes
            ]
        version = sha256(
            json.dumps(
                projection,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return _ResolvedCombatSeed(
            source_kind=source_kind,
            source_ref=source_ref,
            source_version=version,
            display_name=display_name,
            initiative_bonus=int(initiative_bonus),
            dexterity_modifier=int(dexterity_modifier),
            current_hp=int(max_hp if current_hp is None else current_hp),
            max_hp=int(max_hp),
            temp_hp=int(temp_hp),
            movement_total=int(movement_total),
            resource_counter_seeds=counters,
            resource_note_seeds=notes,
        )

    def _load_dm_statblocks(
        self,
        campaign_slug: str,
        statblock_ids: tuple[int, ...],
    ) -> dict[str, object]:
        if not statblock_ids:
            return {}
        placeholders = ", ".join("?" for _ in statblock_ids)
        rows = get_db().execute(
            f"""
            SELECT *
            FROM campaign_dm_statblocks
            WHERE campaign_slug = ? AND id IN ({placeholders})
            ORDER BY id
            """,
            (campaign_slug, *statblock_ids),
        ).fetchall()
        mapper = getattr(self.dm_content_service.store, "_map_statblock")
        return {
            str(row["id"]): mapper(row)
            for row in rows
        }

    @staticmethod
    def _require_available(resolution: _SourceResolution) -> _ResolvedCombatSeed:
        if resolution.status == SOURCE_STATUS_SOURCE_DISABLED:
            raise CampaignCombatPresetSourceValidationError(
                "An encounter preset source is disabled."
            )
        if resolution.status == SOURCE_STATUS_ENTRY_DISABLED:
            raise CampaignCombatPresetSourceValidationError(
                "An encounter preset source entry is disabled."
            )
        if resolution.status != SOURCE_STATUS_CURRENT or resolution.seed is None:
            raise CampaignCombatPresetSourceValidationError(
                "An encounter preset source is missing or inaccessible."
            )
        return resolution.seed

    @staticmethod
    def _exact_text(value: object, field_name: str) -> str:
        if not isinstance(value, str) or value != value.strip():
            raise CampaignCombatPresetSourceValidationError(f"Invalid {field_name}.")
        return value

    @staticmethod
    def _bounded_int(
        value: Any,
        field_name: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        if isinstance(value, bool):
            raise CampaignCombatPresetSourceValidationError(f"Invalid {field_name}.")
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str):
            normalized = value.strip()
            if not normalized or not normalized.lstrip("+-").isdecimal():
                raise CampaignCombatPresetSourceValidationError(f"Invalid {field_name}.")
            parsed = int(normalized)
        else:
            raise CampaignCombatPresetSourceValidationError(f"Invalid {field_name}.")
        if minimum is not None and parsed < minimum:
            raise CampaignCombatPresetSourceValidationError(f"Invalid {field_name}.")
        if maximum is not None and parsed > maximum:
            raise CampaignCombatPresetSourceValidationError(f"Invalid {field_name}.")
        return parsed
