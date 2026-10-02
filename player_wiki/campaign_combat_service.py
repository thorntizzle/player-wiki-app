from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import re
import threading
import time
from collections import defaultdict
from typing import Any, Callable

from yaml import YAMLError

from .campaign_combat_store import (
    CampaignCombatConflictError,
    CampaignCombatRevisionConflictError,
    CampaignCombatStore,
)
from .db import get_db
from .character_repository import (
    CharacterRepository,
    CharacterSnapshotSourceFileToken,
)
from .character_store import (
    CharacterStateConflictError, source_write_transaction, source_writer_reserved,
)
from .character_state_service import CharacterStateService
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_MANUAL_NPC,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
    COMBAT_SOURCE_KINDS,
    CampaignCombatConditionRecord,
    CampaignCombatantRecord,
    CampaignCombatantResourceCounterRecord,
    CampaignCombatantResourceNoteRecord,
    CampaignCombatTrackerRecord,
)
from .combat_npc_resources import NpcResourceCounterSeed, NpcResourceNoteSeed
from .divine_avatar_forms import divine_avatar_forms_state_from

MOVEMENT_VALUE_PATTERN = re.compile(r"(?P<distance>\d+)")


@dataclass
class PlayerCharacterSnapshotSyncMetrics:
    status: str
    lock_wait_ms: float = 0.0
    sync_elapsed_ms: float = 0.0
    sync_ran: bool = False
    sync_changed: bool = False
    lock_acquired: bool = False

    def to_diagnostics_payload(self) -> dict[str, object]:
        return {
            "snapshot_sync_status": self.status,
            "snapshot_sync_lock_wait_ms": round(self.lock_wait_ms, 2),
            "snapshot_sync_ms": round(self.sync_elapsed_ms, 2),
            "snapshot_sync_ran": self.sync_ran,
            "snapshot_sync_changed": self.sync_changed,
            "snapshot_sync_lock_acquired": self.lock_acquired,
        }


SNAPSHOT_SYNC_STATUS_PRE_LOCK_THROTTLED = "skipped_throttle_pre_lock"
SNAPSHOT_SYNC_STATUS_POST_LOCK_THROTTLED = "skipped_throttle_post_lock"
SNAPSHOT_SYNC_STATUS_LOCK_HELD = "skipped_lock_busy_nonblocking"
SNAPSHOT_SYNC_STATUS_TOKEN_UNCHANGED = "skipped_unchanged_source_token"
SNAPSHOT_SYNC_STATUS_SYNCED = "synced"
SNAPSHOT_SYNC_STATUS_DEFERRED = "deferred_conflict"
PLAYER_SNAPSHOT_SYNC_MAX_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class _PlayerCharacterSnapshotDatabaseToken:
    combatant_id: int
    character_slug: str
    display_name: str
    initiative_bonus: int
    dexterity_modifier: int
    current_hp: int
    max_hp: int
    temp_hp: int
    movement_total: int
    movement_remaining: int
    character_state_revision: int | None
    reconciliation_protected: bool


@dataclass(frozen=True, slots=True)
class _PlayerCharacterSnapshotSourceToken:
    database: tuple[_PlayerCharacterSnapshotDatabaseToken, ...]
    files: CharacterSnapshotSourceFileToken
    authorities: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _PlayerCharacterSnapshotFullSyncResult:
    changed: bool
    loaded_character_slugs: frozenset[str]
    deferred: bool = False


class CampaignCombatValidationError(ValueError):
    pass


@contextmanager
def _combat_source_write_transaction():
    try:
        with source_write_transaction():
            yield
    except CharacterStateConflictError as exc:
        raise CampaignCombatValidationError(str(exc)) from exc


def parse_combat_movement_total(value: Any | None) -> int:
    normalized = str(value or "").strip()
    distances = [
        int(match.group("distance"))
        for match in MOVEMENT_VALUE_PATTERN.finditer(normalized)
    ]
    return max(distances) if distances else 0


def extract_combat_dexterity_modifier(stats: dict[str, Any]) -> int:
    raw_ability_scores = stats.get("ability_scores") or {}
    if not isinstance(raw_ability_scores, dict):
        return 0
    ability_scores = dict(raw_ability_scores)
    dexterity = (
        ability_scores.get("dex")
        or ability_scores.get("DEX")
        or ability_scores.get("dexterity")
        or ability_scores.get("Dexterity")
        or ability_scores.get("DEXTERITY")
        or {}
    )
    if isinstance(dexterity, (int, float, str)):
        raw_modifier = None
        raw_score = dexterity
    elif isinstance(dexterity, dict):
        raw_modifier = dexterity.get("modifier")
        raw_score = dexterity.get("score")
    else:
        return 0
    if raw_modifier is not None and str(raw_modifier).strip() != "":
        try:
            return int(raw_modifier)
        except (TypeError, ValueError):
            return 0
    if raw_score is None or str(raw_score).strip() == "":
        return 0
    try:
        return (int(raw_score) - 10) // 2
    except (TypeError, ValueError):
        return 0


def build_character_combat_seed(definition: object) -> dict[str, int | str]:
    stats = dict(getattr(definition, "stats", {}) or {})
    return {
        "source_ref": str(getattr(definition, "character_slug", "") or ""),
        "display_name": str(getattr(definition, "name", "") or ""),
        "initiative_bonus": int(stats.get("initiative_bonus") or 0),
        "dexterity_modifier": extract_combat_dexterity_modifier(stats),
        "max_hp": int(stats.get("max_hp") or 0),
        "movement_total": parse_combat_movement_total(stats.get("speed")),
    }


def build_character_combat_snapshot(record: object, *, source_authority: Any | None = None) -> dict[str, int | str]:
    definition = getattr(record, "definition", None)
    from .committed_publication import active
    from .system_policy import is_xianxia_system
    activated = active()
    if not activated or is_xianxia_system(getattr(definition, "system", "")):
        seed = build_character_combat_seed(definition)
        state_record = getattr(record, "state_record", None)
        state = dict(getattr(state_record, "state", {}) or {})
        vitals = dict(state.get("vitals") or {})
        return {
            **seed,
            "current_hp": int(vitals.get("current_hp") or 0),
            "temp_hp": int(vitals.get("temp_hp") or 0),
        }
    if source_authority is None:
        raise CampaignCombatValidationError("Character numeric authority is unavailable for Combat.")
    required = {
        "initiative_bonus": "stats.initiative_bonus",
        "dexterity_modifier": "stats.ability_scores.dex.modifier",
        "max_hp": "stats.max_hp",
        "movement_total": "stats.speed",
    }
    values: dict[str, int] = {}
    for label, path in required.items():
        status = source_authority.field_status(path)
        if not status.is_effective:
            raise CampaignCombatValidationError("Character numeric values need manager repair before Combat automation.")
        if label == "movement_total":
            if MOVEMENT_VALUE_PATTERN.search(str(status.effective or "")) is None:
                raise CampaignCombatValidationError("Movement speed needs manager repair before Combat automation.")
            values[label] = parse_combat_movement_total(status.effective)
        else:
            values[label] = int(status.effective)
    state_record = getattr(record, "state_record", None)
    state = dict(getattr(state_record, "state", {}) or {})
    vitals = dict(state.get("vitals") or {})
    current_hp = int(vitals.get("current_hp") or 0)
    temp_hp = int(vitals.get("temp_hp") or 0)
    if current_hp < 0 or current_hp > values["max_hp"] or temp_hp < 0:
        raise CampaignCombatValidationError("Character HP needs review before Combat automation.")
    return {
        "source_ref": str(getattr(definition, "character_slug", "") or ""),
        "display_name": str(getattr(definition, "name", "") or ""),
        **values,
        "current_hp": current_hp,
        "temp_hp": temp_hp,
    }


def _normalize_seed_int(
    value: Any | None,
    *,
    label: str,
    default: int | None,
    minimum: int | None = 0,
) -> int:
    normalized = "" if value is None else str(value).strip()
    if not normalized:
        if default is None:
            raise CampaignCombatValidationError(f"{label} is required.")
        parsed = default
    else:
        try:
            parsed = int(normalized)
        except ValueError as exc:
            raise CampaignCombatValidationError(f"{label} must be a whole number.") from exc
    if minimum is not None and parsed < minimum:
        raise CampaignCombatValidationError(f"{label} must be {minimum} or higher.")
    return parsed


def normalize_npc_resource_counter_seeds(
    seeds: list[object] | tuple[object, ...],
) -> tuple[NpcResourceCounterSeed, ...]:
    normalized_seeds: list[NpcResourceCounterSeed] = []
    seen_keys: set[str] = set()
    for seed in seeds:
        resource_key = str(getattr(seed, "resource_key", "") or "").strip()
        label = str(getattr(seed, "label", "") or "").strip()
        if not resource_key or not label or resource_key in seen_keys:
            continue
        max_value = _normalize_seed_int(
            getattr(seed, "max_value", None),
            label=f"{label} maximum",
            default=None,
            minimum=1,
        )
        current_value = _normalize_seed_int(
            getattr(seed, "current_value", None),
            label=f"{label} current value",
            default=max_value,
            minimum=0,
        )
        reset_kind = str(getattr(seed, "reset_kind", "source") or "").strip()
        recharge_threshold_raw = getattr(seed, "recharge_threshold", None)
        if reset_kind not in {"source", "daily", "recharge_d6"}:
            raise CampaignCombatValidationError(f"{label} has an invalid reset kind.")
        recharge_threshold: int | None = None
        if reset_kind == "recharge_d6":
            recharge_threshold = _normalize_seed_int(
                recharge_threshold_raw,
                label=f"{label} recharge threshold",
                default=None,
                minimum=2,
            )
            if recharge_threshold > 6:
                raise CampaignCombatValidationError(
                    f"{label} recharge threshold must be 6 or lower."
                )
            if current_value != 1 or max_value != 1:
                raise CampaignCombatValidationError(
                    f"{label} recharge counters must be one-use counters."
                )
        elif recharge_threshold_raw is not None:
            raise CampaignCombatValidationError(
                f"{label} cannot have a recharge threshold without recharge reset metadata."
            )
        seen_keys.add(resource_key)
        normalized_seeds.append(
            NpcResourceCounterSeed(
                resource_key=resource_key[:80],
                label=label[:120],
                current_value=min(current_value, max_value),
                max_value=max_value,
                reset_label=(
                    ("Recharge 6" if recharge_threshold == 6 else f"Recharge {recharge_threshold}\u20136")
                    if recharge_threshold is not None
                    else str(getattr(seed, "reset_label", "") or "").strip()[:80]
                ),
                source_label=str(getattr(seed, "source_label", "") or "").strip()[:120],
                reset_kind=reset_kind,
                recharge_threshold=recharge_threshold,
            )
        )
    return tuple(normalized_seeds)


def normalize_npc_resource_note_seeds(
    seeds: list[object] | tuple[object, ...],
) -> tuple[NpcResourceNoteSeed, ...]:
    normalized_seeds: list[NpcResourceNoteSeed] = []
    seen_notes: set[tuple[str, str]] = set()
    for seed in seeds:
        label = str(getattr(seed, "label", "") or "").strip()
        note = str(getattr(seed, "note", "") or "").strip()
        if not label or not note:
            continue
        note_key = (label.lower(), note.lower())
        if note_key in seen_notes:
            continue
        seen_notes.add(note_key)
        normalized_seeds.append(
            NpcResourceNoteSeed(
                label=label[:120],
                note=note[:300],
                source_label=str(getattr(seed, "source_label", "") or "").strip()[:120],
            )
        )
    return tuple(normalized_seeds)


class CampaignCombatService:
    def __init__(
        self,
        store: CampaignCombatStore,
        character_repository: CharacterRepository,
        character_state_service: CharacterStateService,
        *,
        session_revision_callback: Callable[..., None] | None = None,
        player_snapshot_sync_interval_seconds: float = 0.0,
    ) -> None:
        self.store = store
        self.character_repository = character_repository
        self.character_state_service = character_state_service
        self.session_revision_callback = session_revision_callback
        self.source_resolver = None
        self.player_snapshot_sync_interval_seconds = max(
            0.0,
            float(player_snapshot_sync_interval_seconds),
        )
        self._player_snapshot_sync_lock = threading.Lock()
        self._player_snapshot_sync_completed_at: dict[str, float] = {}
        self._player_snapshot_sync_source_tokens: dict[
            str,
            _PlayerCharacterSnapshotSourceToken,
        ] = {}

    def get_tracker(self, campaign_slug: str) -> CampaignCombatTrackerRecord:
        return self.store.ensure_tracker(campaign_slug)

    def get_live_revision(self, campaign_slug: str) -> int:
        return self.store.ensure_tracker(campaign_slug).revision

    def list_combatants(
        self,
        campaign_slug: str,
        *,
        sync_player_character_snapshots: bool = True,
    ) -> list[CampaignCombatantRecord]:
        if sync_player_character_snapshots:
            self.sync_player_character_snapshots(campaign_slug)
        return self.store.list_combatants(campaign_slug)

    def get_combatant(self, campaign_slug: str, combatant_id: int) -> CampaignCombatantRecord | None:
        return self.store.get_combatant(campaign_slug, combatant_id)

    def list_conditions_by_combatant(
        self,
        campaign_slug: str,
        *,
        combatant_ids: list[int] | None = None,
    ) -> dict[int, list[CampaignCombatConditionRecord]]:
        if combatant_ids is None:
            combatants = self.store.list_combatants(campaign_slug)
            combatant_ids = [combatant.id for combatant in combatants]
        conditions = self.store.list_conditions(
            campaign_slug,
            combatant_ids=combatant_ids,
        )
        grouped: dict[int, list[CampaignCombatConditionRecord]] = defaultdict(list)
        for condition in conditions:
            grouped[condition.combatant_id].append(condition)
        return dict(grouped)

    def list_resource_counters_by_combatant(
        self,
        campaign_slug: str,
        *,
        combatant_ids: list[int] | None = None,
    ) -> dict[int, list[CampaignCombatantResourceCounterRecord]]:
        if combatant_ids is None:
            combatants = self.store.list_combatants(campaign_slug)
            combatant_ids = [combatant.id for combatant in combatants]
        counters = self.store.list_resource_counters(
            campaign_slug,
            combatant_ids=combatant_ids,
        )
        grouped: dict[int, list[CampaignCombatantResourceCounterRecord]] = defaultdict(list)
        for counter in counters:
            grouped[counter.combatant_id].append(counter)
        return dict(grouped)

    def list_resource_notes_by_combatant(
        self,
        campaign_slug: str,
        *,
        combatant_ids: list[int] | None = None,
    ) -> dict[int, list[CampaignCombatantResourceNoteRecord]]:
        if combatant_ids is None:
            combatants = self.store.list_combatants(campaign_slug)
            combatant_ids = [combatant.id for combatant in combatants]
        notes = self.store.list_resource_notes(
            campaign_slug,
            combatant_ids=combatant_ids,
        )
        grouped: dict[int, list[CampaignCombatantResourceNoteRecord]] = defaultdict(list)
        for note in notes:
            grouped[note.combatant_id].append(note)
        return dict(grouped)

    def list_available_player_characters(self, campaign_slug: str):
        existing_slugs = {
            combatant.character_slug
            for combatant in self.store.list_combatants(campaign_slug)
            if combatant.character_slug
        }
        return [
            record
            for record in self.character_repository.list_visible_characters(campaign_slug)
            if record.definition.character_slug not in existing_slugs
        ]

    def add_player_character(
        self,
        campaign_slug: str,
        *,
        character_slug: str,
        turn_value: Any | None = None,
        initiative_priority: Any | None = None,
        created_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        from .committed_publication import active
        if active() and not source_writer_reserved(get_db()):
            # Reject malformed request values before waiting for a writer.
            if turn_value is not None and str(turn_value).strip():
                self._parse_int(turn_value, label="Turn value", default=None, minimum=None)
            self._parse_initiative_priority(initiative_priority, default=1)
            with _combat_source_write_transaction():
                return self.add_player_character(
                    campaign_slug, character_slug=character_slug, turn_value=turn_value,
                    initiative_priority=initiative_priority, created_by_user_id=created_by_user_id,
                )
        record = (self._load_current_player_character(campaign_slug, character_slug)
                  if active() else self.character_repository.get_visible_character(campaign_slug, character_slug))
        if record is None:
            raise CampaignCombatValidationError("Choose a valid player character to add to the tracker.")

        try:
            snapshot = self._build_player_character_snapshot(record)
        except ValueError as exc:
            raise CampaignCombatValidationError(str(exc)) from exc
        normalized_turn_value = self._parse_int(
            turn_value,
            label="Turn value",
            default=snapshot["initiative_bonus"],
            minimum=None,
        )
        normalized_initiative_priority = self._parse_initiative_priority(
            initiative_priority,
            default=1,
        )

        try:
            with get_db() as connection:
                self.store.ensure_tracker(
                    campaign_slug,
                    updated_by_user_id=created_by_user_id,
                    commit=False,
                )
                combatant = self.store.create_combatant(
                    campaign_slug,
                    combatant_type="player_character",
                    character_slug=record.definition.character_slug,
                    player_detail_visible=True,
                    source_kind=COMBAT_SOURCE_KIND_CHARACTER,
                    source_ref=record.definition.character_slug,
                    display_name=record.definition.name,
                    turn_value=normalized_turn_value,
                    initiative_bonus=snapshot["initiative_bonus"],
                    dexterity_modifier=snapshot["dexterity_modifier"],
                    initiative_priority=normalized_initiative_priority,
                    current_hp=snapshot["current_hp"],
                    max_hp=snapshot["max_hp"],
                    temp_hp=snapshot["temp_hp"],
                    movement_total=snapshot["movement_total"],
                    movement_remaining=snapshot["movement_total"],
                    created_by_user_id=created_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=created_by_user_id,
                    commit=False,
                )
            return combatant
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError(
                "That player character is already in the combat tracker."
            ) from exc

    def add_npc_combatant(
        self,
        campaign_slug: str,
        *,
        display_name: str,
        turn_value: Any | None,
        initiative_bonus: Any | None = 0,
        dexterity_modifier: Any | None = None,
        initiative_priority: Any | None = None,
        current_hp: Any | None,
        max_hp: Any | None,
        temp_hp: Any | None = 0,
        movement_total: Any | None = 0,
        source_kind: str = COMBAT_SOURCE_KIND_MANUAL_NPC,
        source_ref: str = "",
        display_name_is_override: bool = False,
        turn_value_is_override: bool = False,
        resource_counter_seeds: list[object] | None = None,
        resource_note_seeds: list[object] | None = None,
        created_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        normalized_name = (display_name or "").strip()
        if not normalized_name:
            raise CampaignCombatValidationError("NPC name is required.")

        normalized_turn_value = self._parse_int(turn_value, label="Turn value", default=0, minimum=None)
        normalized_initiative_bonus = self._parse_int(
            initiative_bonus,
            label="Initiative bonus",
            default=0,
            minimum=None,
        )
        normalized_dexterity_modifier = self._parse_int(
            dexterity_modifier,
            label="Dexterity modifier",
            default=normalized_initiative_bonus,
            minimum=None,
        )
        normalized_initiative_priority = self._parse_initiative_priority(
            initiative_priority,
            default=1,
        )
        normalized_max_hp = self._parse_int(max_hp, label="Max HP", default=None, minimum=0)
        normalized_current_hp = self._parse_int(
            current_hp,
            label="Current HP",
            default=normalized_max_hp,
            minimum=0,
        )
        normalized_temp_hp = self._parse_int(temp_hp, label="Temp HP", default=0, minimum=0)
        normalized_movement_total = self._parse_int(
            movement_total,
            label="Movement",
            default=0,
            minimum=0,
        )
        normalized_source_kind = str(source_kind or "").strip() or COMBAT_SOURCE_KIND_MANUAL_NPC
        if normalized_source_kind not in COMBAT_SOURCE_KINDS:
            raise CampaignCombatValidationError("Choose a valid NPC source.")
        normalized_source_ref = str(source_ref or "").strip()
        if normalized_source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
            normalized_source_ref = ""
        if normalized_current_hp > normalized_max_hp:
            raise CampaignCombatValidationError("Current HP cannot exceed max HP.")
        normalized_counter_seeds = self._normalize_resource_counter_seeds(resource_counter_seeds or [])
        normalized_note_seeds = self._normalize_resource_note_seeds(resource_note_seeds or [])
        if normalized_source_kind == COMBAT_SOURCE_KIND_MANUAL_NPC:
            normalized_counter_seeds = []
            normalized_note_seeds = []

        from .committed_publication import active
        if active() and normalized_source_kind != COMBAT_SOURCE_KIND_MANUAL_NPC:
            if self.source_resolver is None:
                raise CampaignCombatValidationError("Combat source resolver is unavailable.")
            try:
                if not source_writer_reserved(get_db()):
                    basis = self.source_resolver.resolve_source_for_action(
                        campaign_slug, normalized_source_kind, normalized_source_ref,
                        require_reservation=False,
                    )
                    with _combat_source_write_transaction():
                        locked = self.source_resolver.resolve_source_for_action(
                            campaign_slug, normalized_source_kind, normalized_source_ref,
                        )
                        if locked.source_version != basis.source_version:
                            raise CampaignCombatValidationError("NPC source changed. Refresh before adding it.")
                        return self.add_npc_combatant(
                            campaign_slug, display_name=display_name, turn_value=turn_value,
                            initiative_bonus=initiative_bonus,
                            dexterity_modifier=dexterity_modifier,
                            initiative_priority=initiative_priority, current_hp=current_hp,
                            max_hp=max_hp, temp_hp=temp_hp, movement_total=movement_total,
                            source_kind=source_kind, source_ref=source_ref,
                            display_name_is_override=display_name_is_override,
                            turn_value_is_override=turn_value_is_override,
                            resource_counter_seeds=resource_counter_seeds,
                            resource_note_seeds=resource_note_seeds,
                            created_by_user_id=created_by_user_id,
                        )
                locked = self.source_resolver.resolve_source_for_action(
                    campaign_slug, normalized_source_kind, normalized_source_ref,
                )
            except ValueError as exc:
                raise CampaignCombatValidationError(str(exc)) from exc
            if (
                (not display_name_is_override and normalized_name != locked.display_name)
                or (not turn_value_is_override and normalized_turn_value != locked.initiative_bonus)
                or
                normalized_initiative_bonus != locked.initiative_bonus
                or normalized_dexterity_modifier != locked.dexterity_modifier
                or normalized_max_hp != locked.max_hp
                or normalized_current_hp != locked.current_hp
                or normalized_temp_hp != locked.temp_hp
                or normalized_movement_total != locked.movement_total
                or tuple(normalized_counter_seeds) != locked.resource_counter_seeds
                or tuple(normalized_note_seeds) != locked.resource_note_seeds
            ):
                raise CampaignCombatValidationError("NPC source changed. Refresh before adding it.")

        with get_db() as connection:
            self.store.ensure_tracker(
                campaign_slug,
                updated_by_user_id=created_by_user_id,
                commit=False,
            )
            combatant = self.store.create_combatant(
                campaign_slug,
                combatant_type="npc",
                player_detail_visible=False,
                source_kind=normalized_source_kind,
                source_ref=normalized_source_ref,
                display_name=normalized_name,
                turn_value=normalized_turn_value,
                initiative_bonus=normalized_initiative_bonus,
                dexterity_modifier=normalized_dexterity_modifier,
                initiative_priority=normalized_initiative_priority,
                current_hp=normalized_current_hp,
                max_hp=normalized_max_hp,
                temp_hp=normalized_temp_hp,
                movement_total=normalized_movement_total,
                movement_remaining=normalized_movement_total,
                created_by_user_id=created_by_user_id,
                commit=False,
            )
            self.store.create_resource_counters(
                combatant.id,
                normalized_counter_seeds,
                created_by_user_id=created_by_user_id,
                commit=False,
            )
            self.store.create_resource_notes(
                combatant.id,
                normalized_note_seeds,
                created_by_user_id=created_by_user_id,
                commit=False,
            )
            self.store.bump_tracker_revision(
                campaign_slug,
                updated_by_user_id=created_by_user_id,
                commit=False,
            )
        return combatant

    def update_turn_value(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int | None = None,
        turn_value: Any | None,
        initiative_priority: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        normalized_turn_value = self._parse_int(
            turn_value,
            label="Turn value",
            default=combatant.turn_value,
            minimum=None,
        )
        normalized_initiative_priority = self._parse_initiative_priority(
            initiative_priority,
            default=combatant.initiative_priority,
        )
        try:
            with get_db() as connection:
                combatant = self.store.update_combatant(
                    campaign_slug,
                    combatant_id,
                    turn_value=normalized_turn_value,
                    initiative_priority=normalized_initiative_priority,
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
            return combatant
        except CampaignCombatRevisionConflictError:
            raise
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("That turn value could not be saved.") from exc

    def update_npc_vitals(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int | None = None,
        current_hp: Any | None,
        max_hp: Any | None,
        temp_hp: Any | None = 0,
        movement_total: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        if not combatant.is_npc:
            raise CampaignCombatValidationError("Only NPC vitals can be edited directly here.")

        normalized_max_hp = self._parse_int(max_hp, label="Max HP", default=combatant.max_hp, minimum=0)
        normalized_current_hp = self._parse_int(
            current_hp,
            label="Current HP",
            default=combatant.current_hp,
            minimum=0,
        )
        normalized_temp_hp = self._parse_int(
            temp_hp,
            label="Temp HP",
            default=combatant.temp_hp,
            minimum=0,
        )
        normalized_movement_total = self._parse_int(
            movement_total,
            label="Movement",
            default=combatant.movement_total,
            minimum=0,
        )
        if normalized_current_hp > normalized_max_hp:
            raise CampaignCombatValidationError("Current HP cannot exceed max HP.")

        try:
            with get_db() as connection:
                updated_combatant = self.store.update_combatant(
                    campaign_slug,
                    combatant_id,
                    current_hp=normalized_current_hp,
                    max_hp=normalized_max_hp,
                    temp_hp=normalized_temp_hp,
                    movement_total=normalized_movement_total,
                    movement_remaining=min(combatant.movement_remaining, normalized_movement_total),
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
            return updated_combatant
        except CampaignCombatRevisionConflictError:
            raise
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("Those NPC vitals could not be saved.") from exc

    def update_player_character_vitals(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int,
        current_hp: Any | None,
        temp_hp: Any | None,
        hit_dice_current: dict[int, Any] | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        from .committed_publication import active
        if active() and not source_writer_reserved(get_db()):
            with _combat_source_write_transaction():
                return self.update_player_character_vitals(
                    campaign_slug, combatant_id, expected_revision=expected_revision,
                    current_hp=current_hp, temp_hp=temp_hp,
                    hit_dice_current=hit_dice_current, updated_by_user_id=updated_by_user_id,
                )
        combatant = self._require_combatant(campaign_slug, combatant_id)
        if not combatant.is_player_character or not combatant.character_slug:
            raise CampaignCombatValidationError("Only player-character vitals can be edited here.")

        record = (self._load_current_player_character(campaign_slug, combatant.character_slug)
                  if active() else self.character_repository.get_visible_character(
                      campaign_slug, combatant.character_slug))
        if record is None:
            raise CampaignCombatValidationError("That player character could not be loaded from the campaign data.")

        activated = active(get_db())
        try:
            authority = self.character_state_service.current_authority(record) if activated else None
        except ValueError as exc:
            raise CampaignCombatValidationError(str(exc)) from exc
        max_hp_status = authority.field_status("stats.max_hp") if authority is not None else None
        hp_edit = current_hp is not None or temp_hp is not None
        from .system_policy import is_xianxia_system
        dnd_authority_required = activated and not is_xianxia_system(record.definition.system)
        if dnd_authority_required and hp_edit and (max_hp_status is None or not max_hp_status.is_effective):
            raise CampaignCombatValidationError("Character HP needs manager repair before Combat automation.")
        if dnd_authority_required:
            max_hp = int(max_hp_status.effective) if hp_edit else None
        else:
            max_hp = int(record.definition.stats.get("max_hp") or 0)
        try:
            with get_db() as connection:
                state_record = self.character_state_service.update_vitals(
                    record,
                    expected_revision=expected_revision,
                    current_hp=current_hp,
                    temp_hp=temp_hp,
                    hit_dice_current=hit_dice_current,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                # The Character CAS now holds the writer reservation. The
                # activated path keeps unresolved encounter fields as table
                # state; the closed path refreshes the legacy saved seed.
                current_combatant = self._require_combatant(campaign_slug, combatant_id)
                if (
                    not current_combatant.is_player_character
                    or current_combatant.character_slug != combatant.character_slug
                ):
                    raise CampaignCombatValidationError("Only player-character vitals can be edited here.")
                legacy_snapshot = (build_character_combat_seed(record.definition)
                                   if not dnd_authority_required else None)
                updated_combatant = self.store.update_combatant(
                    campaign_slug,
                    combatant_id,
                    display_name=legacy_snapshot["display_name"] if legacy_snapshot is not None else None,
                    initiative_bonus=legacy_snapshot["initiative_bonus"] if legacy_snapshot is not None else None,
                    dexterity_modifier=legacy_snapshot["dexterity_modifier"] if legacy_snapshot is not None else None,
                    current_hp=(int((state_record.state.get("vitals") or {}).get("current_hp") or 0)
                                if hp_edit or not dnd_authority_required else None),
                    max_hp=max_hp,
                    temp_hp=(int((state_record.state.get("vitals") or {}).get("temp_hp") or 0)
                             if hp_edit or not dnd_authority_required else None),
                    movement_total=legacy_snapshot["movement_total"] if legacy_snapshot is not None else None,
                    movement_remaining=(min(current_combatant.movement_remaining,
                                            legacy_snapshot["movement_total"])
                                        if legacy_snapshot is not None else None),
                    expected_revision=current_combatant.revision,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                if self.session_revision_callback is not None:
                    self.session_revision_callback(
                        campaign_slug,
                        updated_by_user_id=updated_by_user_id,
                        commit=False,
                    )
            return updated_combatant
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("That combat tracker row could not be updated.") from exc

    def update_resources(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int | None = None,
        has_action: bool | None = None,
        has_bonus_action: bool | None = None,
        has_reaction: bool | None = None,
        movement_remaining: Any | None = None,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        from .committed_publication import active
        if active() and not source_writer_reserved(get_db()):
            with _combat_source_write_transaction():
                return self.update_resources(
                    campaign_slug, combatant_id, expected_revision=expected_revision,
                    has_action=has_action, has_bonus_action=has_bonus_action,
                    has_reaction=has_reaction, movement_remaining=movement_remaining,
                    updated_by_user_id=updated_by_user_id,
                )
        combatant = self._require_combatant(campaign_slug, combatant_id)
        activated = active()
        if activated and combatant.is_player_character and combatant.character_slug:
            if (type(expected_revision) is not int or expected_revision < 1
                    or combatant.revision != expected_revision):
                raise CampaignCombatRevisionConflictError(
                    "This combatant changed in another combat view. Refresh and try again."
                )
        normalized_movement_remaining = self._parse_int(
            movement_remaining,
            label="Remaining movement",
            default=combatant.movement_remaining,
            minimum=0,
        )
        movement_total_for_write = None
        movement_authority_identity = None
        legacy_movement_limit = not activated
        if (combatant.is_player_character and combatant.character_slug
                and (movement_remaining is not None if activated else
                     normalized_movement_remaining != combatant.movement_remaining)):
            character_record = (self._load_current_player_character(
                campaign_slug, combatant.character_slug,
            ) if activated else self.character_repository.get_combat_seed_character(
                campaign_slug, combatant.character_slug,
            ))
            if character_record is None:
                raise CampaignCombatValidationError("Character movement source is unavailable.")
            try:
                movement_authority = self.character_state_service.current_authority(character_record)
            except ValueError as exc:
                raise CampaignCombatValidationError("Character movement source is unavailable.") from exc
            if (movement_authority is not None
                    and not movement_authority.field_status("stats.speed").is_effective):
                raise CampaignCombatValidationError("Movement speed needs manager repair before it can change.")
            from .system_policy import is_xianxia_system
            legacy_movement_limit = legacy_movement_limit or is_xianxia_system(
                character_record.definition.system
            )
            if activated and not is_xianxia_system(character_record.definition.system):
                if movement_authority is None:
                    raise CampaignCombatValidationError("Movement speed needs manager repair before it can change.")
                movement_total_for_write = parse_combat_movement_total(
                    movement_authority.field_status("stats.speed").effective,
                )
                if MOVEMENT_VALUE_PATTERN.search(
                    str(movement_authority.field_status("stats.speed").effective or "")
                ) is None:
                    raise CampaignCombatValidationError("Movement speed needs manager repair before it can change.")
                if normalized_movement_remaining > movement_total_for_write:
                    raise CampaignCombatValidationError("Remaining movement cannot exceed current speed.")
            movement_authority_identity = movement_authority.identity if movement_authority is not None else None
        if legacy_movement_limit and normalized_movement_remaining > combatant.movement_total:
            raise CampaignCombatValidationError("Remaining movement cannot exceed total movement.")

        try:
            with get_db() as connection:
                if movement_authority_identity is not None:
                    refreshed_record = (self._load_current_player_character(
                        campaign_slug, combatant.character_slug,
                    ) if activated else self.character_repository.get_combat_seed_character(
                        campaign_slug, combatant.character_slug,
                    ))
                    try:
                        refreshed_authority = (self.character_state_service.current_authority(refreshed_record)
                                               if refreshed_record is not None else None)
                    except ValueError as exc:
                        raise CampaignCombatValidationError("Character movement source changed. Refresh before saving.") from exc
                    if (refreshed_authority is None
                            or refreshed_authority.identity != movement_authority_identity):
                        raise CampaignCombatValidationError("Character movement source changed. Refresh before saving.")
                updated_combatant = self.store.update_combatant(
                    campaign_slug,
                    combatant_id,
                    has_action=combatant.has_action if has_action is None else has_action,
                    has_bonus_action=(combatant.has_bonus_action if has_bonus_action is None
                                      else has_bonus_action),
                    has_reaction=combatant.has_reaction if has_reaction is None else has_reaction,
                    movement_total=movement_total_for_write,
                    movement_remaining=normalized_movement_remaining,
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
            return updated_combatant
        except CampaignCombatRevisionConflictError:
            raise
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("Those combat resources could not be saved.") from exc

    def update_npc_resource_counters(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int | None = None,
        counter_values: list[dict[str, Any]],
        updated_by_user_id: int | None = None,
    ) -> list[CampaignCombatantResourceCounterRecord]:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        if not combatant.is_npc:
            raise CampaignCombatValidationError("Only NPC source resources can be edited here.")
        if not isinstance(counter_values, list):
            raise CampaignCombatValidationError("NPC resource counters must be sent as a list.")

        existing_counters = self.store.list_resource_counters(campaign_slug, combatant_ids=[combatant_id])
        counters_by_key = {counter.resource_key: counter for counter in existing_counters}
        if not counters_by_key:
            raise CampaignCombatValidationError("This NPC has no supported source-backed resource counters.")

        values_by_key: dict[str, int] = {}
        for index, counter_value in enumerate(counter_values, start=1):
            if not isinstance(counter_value, dict):
                raise CampaignCombatValidationError(f"NPC resource row {index} must be an object.")
            resource_key = str(counter_value.get("resource_key") or "").strip()
            if not resource_key or resource_key not in counters_by_key:
                raise CampaignCombatValidationError("Choose a valid NPC resource counter.")
            counter = counters_by_key[resource_key]
            current_value = self._parse_int(
                counter_value.get("current_value"),
                label=f"{counter.label} current value",
                default=counter.current_value,
                minimum=0,
            )
            if current_value > counter.max_value:
                raise CampaignCombatValidationError(f"{counter.label} cannot exceed {counter.max_value}.")
            values_by_key[resource_key] = current_value

        if not values_by_key:
            raise CampaignCombatValidationError("Choose at least one NPC resource counter to update.")

        try:
            with get_db() as connection:
                self.store.update_combatant(
                    campaign_slug,
                    combatant_id,
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                updated_counters = self.store.update_resource_counter_values(
                    campaign_slug,
                    combatant_id,
                    values_by_key,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
            return updated_counters
        except CampaignCombatRevisionConflictError:
            raise
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("Those NPC resources could not be saved.") from exc

    def update_player_detail_visibility(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        expected_revision: int | None = None,
        player_detail_visible: bool,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        if not combatant.is_npc:
            raise CampaignCombatValidationError("Only NPC combatants can toggle player-facing detail visibility.")

        try:
            with get_db() as connection:
                updated_combatant = self.store.update_combatant(
                    campaign_slug,
                    combatant_id,
                    player_detail_visible=player_detail_visible,
                    expected_revision=expected_revision,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self.store.bump_tracker_revision(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
            return updated_combatant
        except CampaignCombatRevisionConflictError:
            raise
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("That NPC visibility setting could not be saved.") from exc

    def add_condition(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        name: str,
        duration_text: str = "",
        created_by_user_id: int | None = None,
    ) -> CampaignCombatConditionRecord:
        self._require_combatant(campaign_slug, combatant_id)
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise CampaignCombatValidationError("Condition name is required.")
        if len(normalized_name) > 80:
            raise CampaignCombatValidationError("Condition names must stay under 80 characters.")

        normalized_duration = (duration_text or "").strip()
        if len(normalized_duration) > 120:
            raise CampaignCombatValidationError("Condition duration text must stay under 120 characters.")

        with get_db() as connection:
            condition = self.store.create_condition(
                combatant_id,
                name=normalized_name,
                duration_text=normalized_duration,
                created_by_user_id=created_by_user_id,
                commit=False,
            )
            self.store.bump_tracker_revision(
                campaign_slug,
                updated_by_user_id=created_by_user_id,
                commit=False,
            )
        return condition

    def delete_condition(
        self,
        campaign_slug: str,
        condition_id: int,
    ) -> CampaignCombatConditionRecord:
        with get_db() as connection:
            condition = self.store.delete_condition(campaign_slug, condition_id, commit=False)
            if condition is None:
                raise CampaignCombatValidationError("That condition could not be found.")
            self.store.bump_tracker_revision(
                campaign_slug,
                commit=False,
            )
        return condition

    def update_condition(
        self,
        campaign_slug: str,
        condition_id: int,
        *,
        name: str,
        duration_text: str = "",
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatConditionRecord:
        normalized_name = (name or "").strip()
        if not normalized_name:
            raise CampaignCombatValidationError("Condition name is required.")
        if len(normalized_name) > 80:
            raise CampaignCombatValidationError("Condition names must stay under 80 characters.")

        normalized_duration = (duration_text or "").strip()
        if len(normalized_duration) > 120:
            raise CampaignCombatValidationError("Condition duration text must stay under 120 characters.")

        with get_db() as connection:
            condition = self.store.update_condition(
                campaign_slug,
                condition_id,
                name=normalized_name,
                duration_text=normalized_duration,
                commit=False,
            )
            if condition is None:
                raise CampaignCombatValidationError("That condition could not be found.")
            self.store.bump_tracker_revision(
                campaign_slug,
                updated_by_user_id=updated_by_user_id,
                commit=False,
            )
        return condition

    def mark_character_state_changed(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> None:
        self.store.bump_tracker_revision(campaign_slug, updated_by_user_id=updated_by_user_id)

    def delete_combatant(
        self,
        campaign_slug: str,
        combatant_id: int,
    ) -> CampaignCombatantRecord:
        with get_db() as connection:
            combatant = self.store.delete_combatant(campaign_slug, combatant_id, commit=False)
            if combatant is None:
                raise CampaignCombatValidationError("That combatant could not be found.")
            self.store.bump_tracker_revision(campaign_slug, commit=False)
        return combatant

    def clear_tracker(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        try:
            return self.store.clear_tracker(
                campaign_slug,
                updated_by_user_id=updated_by_user_id,
            )
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("The combat tracker could not be cleared.") from exc

    def set_current_turn(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        from .committed_publication import active
        if active() and not source_writer_reserved(get_db()):
            with _combat_source_write_transaction():
                return self.set_current_turn(
                    campaign_slug, combatant_id, updated_by_user_id=updated_by_user_id,
                )
        try:
            with get_db() as connection:
                tracker = self.store.ensure_tracker(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                combatant = self._require_combatant(campaign_slug, combatant_id)
                if tracker.current_combatant_id == combatant.id:
                    return tracker
                self._refresh_combatant_turn_resources(
                    campaign_slug,
                    combatant.id,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                updated_tracker = self.store.update_tracker(
                    campaign_slug,
                    round_number=max(1, tracker.round_number),
                    current_combatant_id=combatant.id,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self._advance_divine_avatar_form_turn(
                    campaign_slug,
                    combatant,
                    updated_tracker,
                    updated_by_user_id=updated_by_user_id,
                )
                return updated_tracker
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("The current turn could not be updated.") from exc

    def advance_turn(
        self,
        campaign_slug: str,
        *,
        updated_by_user_id: int | None = None,
    ) -> CampaignCombatTrackerRecord:
        from .committed_publication import active
        if active() and not source_writer_reserved(get_db()):
            with _combat_source_write_transaction():
                return self.advance_turn(campaign_slug, updated_by_user_id=updated_by_user_id)
        try:
            with get_db() as connection:
                tracker = self.store.ensure_tracker(
                    campaign_slug,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                combatants = self.store.list_combatants(campaign_slug)
                if not combatants:
                    raise CampaignCombatValidationError("Add combatants before advancing turn order.")

                current_index = next(
                    (
                        index
                        for index, combatant in enumerate(combatants)
                        if combatant.id == tracker.current_combatant_id
                    ),
                    None,
                )
                if current_index is None:
                    next_index = 0
                    next_round = max(1, tracker.round_number)
                else:
                    next_index = (current_index + 1) % len(combatants)
                    next_round = tracker.round_number + 1 if next_index == 0 else tracker.round_number

                next_combatant = combatants[next_index]
                self._refresh_combatant_turn_resources(
                    campaign_slug,
                    next_combatant.id,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                updated_tracker = self.store.update_tracker(
                    campaign_slug,
                    round_number=max(1, next_round),
                    current_combatant_id=next_combatant.id,
                    updated_by_user_id=updated_by_user_id,
                    commit=False,
                )
                self._advance_divine_avatar_form_turn(
                    campaign_slug,
                    next_combatant,
                    updated_tracker,
                    updated_by_user_id=updated_by_user_id,
                )
                return updated_tracker
        except CampaignCombatConflictError as exc:
            raise CampaignCombatValidationError("The turn order could not be advanced.") from exc

    def _advance_divine_avatar_form_turn(
        self,
        campaign_slug: str,
        combatant: CampaignCombatantRecord,
        tracker: CampaignCombatTrackerRecord,
        *,
        updated_by_user_id: int | None,
    ) -> None:
        if not combatant.is_player_character or not combatant.character_slug:
            return

        from .committed_publication import active
        record = (self._load_current_player_character(campaign_slug, combatant.character_slug)
                  if active() else self.character_repository.get_visible_character(
                      campaign_slug, combatant.character_slug))
        if record is None:
            raise CampaignCombatValidationError(
                "The current player character could not be loaded, so the turn was not updated."
            )

        active_form = str(
            divine_avatar_forms_state_from(record.state_record.state).get("active_form") or ""
        ).strip()
        if not active_form:
            return

        prior_revision = int(record.state_record.revision)
        try:
            updated_state = self.character_state_service.update_divine_avatar_form(
                record,
                active_form,
                "advance_turn",
                expected_revision=prior_revision,
                combat_revision=int(tracker.revision),
                updated_by_user_id=updated_by_user_id,
                commit=False,
            )
        except (CharacterStateConflictError, ValueError) as exc:
            raise CampaignCombatValidationError(
                f"Divine Avatar Form turn tracking failed, so the turn was not updated: {exc}"
            ) from exc

        if (
            int(getattr(updated_state, "revision", prior_revision)) != prior_revision
            and self.session_revision_callback is not None
        ):
            self.session_revision_callback(
                campaign_slug,
                updated_by_user_id=updated_by_user_id,
                commit=False,
            )

    def sync_player_character_snapshots(
        self,
        campaign_slug: str,
        *,
        blocking: bool = True,
    ) -> PlayerCharacterSnapshotSyncMetrics:
        from .committed_publication import active
        if active():
            return self._sync_activated_player_character_snapshots(
                campaign_slug, blocking=blocking,
            )
        sync_interval_seconds = self.player_snapshot_sync_interval_seconds
        metrics = PlayerCharacterSnapshotSyncMetrics(status=SNAPSHOT_SYNC_STATUS_SYNCED)

        now = time.monotonic()
        last_synced_at = self._player_snapshot_sync_completed_at.get(campaign_slug)
        if (
            sync_interval_seconds > 0
            and last_synced_at is not None
            and (now - last_synced_at) < sync_interval_seconds
        ):
            metrics.status = SNAPSHOT_SYNC_STATUS_PRE_LOCK_THROTTLED
            return metrics

        lock_started_at = time.perf_counter()
        if not blocking:
            if not self._player_snapshot_sync_lock.acquire(blocking=False):
                metrics.status = SNAPSHOT_SYNC_STATUS_LOCK_HELD
                return metrics
            metrics.lock_acquired = True
            metrics.lock_wait_ms = (time.perf_counter() - lock_started_at) * 1000
        else:
            self._player_snapshot_sync_lock.acquire()
            metrics.lock_acquired = True
            metrics.lock_wait_ms = (time.perf_counter() - lock_started_at) * 1000

        try:
            last_synced_at = self._player_snapshot_sync_completed_at.get(campaign_slug)
            now = time.monotonic()
            if (
                sync_interval_seconds > 0
                and last_synced_at is not None
                and (now - last_synced_at) < sync_interval_seconds
            ):
                metrics.status = SNAPSHOT_SYNC_STATUS_POST_LOCK_THROTTLED
                return metrics

            previous_source_token = self._player_snapshot_sync_source_tokens.get(campaign_slug)
            source_token = self._read_player_character_snapshot_source_token(
                campaign_slug,
                previous=previous_source_token,
            )
            if previous_source_token is not None and source_token == previous_source_token:
                metrics.status = SNAPSHOT_SYNC_STATUS_TOKEN_UNCHANGED
                self._player_snapshot_sync_completed_at[campaign_slug] = time.monotonic()
                return metrics

            metrics.status = SNAPSHOT_SYNC_STATUS_SYNCED
            sync_started_at = time.perf_counter()
            sync_result = self._sync_player_character_snapshots_now(
                campaign_slug,
                source_token=source_token,
            )
            metrics.sync_changed = sync_result.changed
            metrics.sync_ran = True
            metrics.sync_elapsed_ms = (time.perf_counter() - sync_started_at) * 1000
            self._player_snapshot_sync_completed_at[campaign_slug] = time.monotonic()
            if sync_result.deferred:
                metrics.status = SNAPSHOT_SYNC_STATUS_DEFERRED
                self._player_snapshot_sync_source_tokens.pop(campaign_slug, None)
                return metrics
            if source_token is not None and not self._player_snapshot_source_token_is_cacheable(
                source_token, sync_result
            ):
                self._player_snapshot_sync_source_tokens.pop(campaign_slug, None)
            refreshed_source_token = self._read_player_character_snapshot_source_token(
                campaign_slug,
                previous=source_token,
            )
            if (
                source_token is not None
                and refreshed_source_token == source_token
                and self._player_snapshot_source_token_is_cacheable(
                    refreshed_source_token,
                    sync_result,
                )
            ):
                self._player_snapshot_sync_source_tokens[campaign_slug] = refreshed_source_token
        finally:
            if metrics.lock_acquired:
                self._player_snapshot_sync_lock.release()

        return metrics

    def _sync_activated_player_character_snapshots(
        self, campaign_slug: str, *, blocking: bool,
    ) -> PlayerCharacterSnapshotSyncMetrics:
        """Refresh only from committed rows while holding the writer reservation."""
        metrics = PlayerCharacterSnapshotSyncMetrics(status=SNAPSHOT_SYNC_STATUS_SYNCED)
        last_synced_at = self._player_snapshot_sync_completed_at.get(campaign_slug)
        if (self.player_snapshot_sync_interval_seconds > 0
                and last_synced_at is not None
                and time.monotonic() - last_synced_at < self.player_snapshot_sync_interval_seconds):
            metrics.status = SNAPSHOT_SYNC_STATUS_PRE_LOCK_THROTTLED
            return metrics
        started = time.perf_counter()
        acquired = self._player_snapshot_sync_lock.acquire(blocking=blocking)
        if not acquired:
            metrics.status = SNAPSHOT_SYNC_STATUS_LOCK_HELD
            return metrics
        metrics.lock_acquired = True
        metrics.lock_wait_ms = (time.perf_counter() - started) * 1000
        from .committed_publication import CommittedSourceConflict
        try:
            if get_db().in_transaction:
                metrics.status = SNAPSHOT_SYNC_STATUS_DEFERRED
                return metrics
            last_synced_at = self._player_snapshot_sync_completed_at.get(campaign_slug)
            if (self.player_snapshot_sync_interval_seconds > 0
                    and last_synced_at is not None
                    and time.monotonic() - last_synced_at < self.player_snapshot_sync_interval_seconds):
                metrics.status = SNAPSHOT_SYNC_STATUS_POST_LOCK_THROTTLED
                return metrics
            changed = False
            deferred = False
            pending: list[tuple[CampaignCombatantRecord, object, dict[str, int], int]] = []
            with source_write_transaction():
                for combatant in self.store.list_combatants(campaign_slug):
                    if not combatant.is_player_character or not combatant.character_slug:
                        continue
                    try:
                        record = self.character_repository.get_combat_seed_character(
                            campaign_slug, combatant.character_slug,
                        )
                    except (CommittedSourceConflict, CharacterStateConflictError,
                            OSError, TypeError, ValueError, YAMLError):
                        deferred = True
                        continue
                    if record is None:
                        deferred = True
                        continue
                    try:
                        snapshot = self._build_player_character_snapshot(record)
                    except (CampaignCombatValidationError, CommittedSourceConflict,
                            CharacterStateConflictError, ValueError):
                        deferred = True
                        continue
                    remaining = min(combatant.movement_remaining, snapshot["movement_total"])
                    if (
                        combatant.display_name == record.definition.name
                        and combatant.initiative_bonus == snapshot["initiative_bonus"]
                        and combatant.dexterity_modifier == snapshot["dexterity_modifier"]
                        and combatant.current_hp == snapshot["current_hp"]
                        and combatant.max_hp == snapshot["max_hp"]
                        and combatant.temp_hp == snapshot["temp_hp"]
                        and combatant.movement_total == snapshot["movement_total"]
                        and combatant.movement_remaining == remaining
                    ):
                        continue
                    pending.append((combatant, record, snapshot, remaining))
                if not deferred:
                    for combatant, record, snapshot, remaining in pending:
                        self.store.update_combatant(
                            campaign_slug, combatant.id,
                            display_name=record.definition.name,
                            initiative_bonus=snapshot["initiative_bonus"],
                            dexterity_modifier=snapshot["dexterity_modifier"],
                            current_hp=snapshot["current_hp"], max_hp=snapshot["max_hp"],
                            temp_hp=snapshot["temp_hp"],
                            movement_total=snapshot["movement_total"],
                            movement_remaining=remaining,
                            expected_revision=combatant.revision, commit=False,
                        )
                        changed = True
                    if changed:
                        self.store.bump_tracker_revision(campaign_slug, commit=False)
            metrics.sync_changed = changed
            metrics.sync_ran = True
            metrics.status = SNAPSHOT_SYNC_STATUS_DEFERRED if deferred else SNAPSHOT_SYNC_STATUS_SYNCED
            self._player_snapshot_sync_completed_at[campaign_slug] = time.monotonic()
            self._player_snapshot_sync_source_tokens.pop(campaign_slug, None)
            return metrics
        except CharacterStateConflictError:
            metrics.status = SNAPSHOT_SYNC_STATUS_DEFERRED
            return metrics
        finally:
            metrics.sync_elapsed_ms = (time.perf_counter() - started) * 1000
            self._player_snapshot_sync_lock.release()

    def _read_player_character_snapshot_source_token(
        self,
        campaign_slug: str,
        *,
        previous: _PlayerCharacterSnapshotSourceToken | None,
    ) -> _PlayerCharacterSnapshotSourceToken | None:
        try:
            rows = get_db().execute(
                """
                SELECT
                    combatant.id AS combatant_id,
                    combatant.character_slug,
                    combatant.display_name,
                    combatant.initiative_bonus,
                    combatant.dexterity_modifier,
                    combatant.current_hp,
                    combatant.max_hp,
                    combatant.temp_hp,
                    combatant.movement_total,
                    combatant.movement_remaining,
                    character_state.revision AS character_state_revision,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM character_reconciliation_operations AS reconciliation
                            WHERE reconciliation.campaign_slug = combatant.campaign_slug
                              AND reconciliation.character_slug = combatant.character_slug
                              AND reconciliation.state IN (
                                  'prepared',
                                  'repository_pending',
                                  'conflict'
                              )
                        )
                        OR EXISTS (
                            SELECT 1
                            FROM character_deletion_operations AS deletion
                            WHERE deletion.campaign_slug = combatant.campaign_slug
                              AND deletion.character_slug = combatant.character_slug
                              AND deletion.state IN (
                                  'prepared',
                                  'repository_pending',
                                  'conflict'
                              )
                        )
                        THEN 1
                        ELSE 0
                    END AS reconciliation_protected
                FROM campaign_combatants AS combatant
                LEFT JOIN character_state
                  ON character_state.campaign_slug = combatant.campaign_slug
                 AND character_state.character_slug = combatant.character_slug
                WHERE combatant.campaign_slug = ?
                  AND combatant.combatant_type = 'player_character'
                ORDER BY combatant.id ASC
                """,
                (campaign_slug,),
            ).fetchall()
            database_token = tuple(
                _PlayerCharacterSnapshotDatabaseToken(
                    combatant_id=int(row["combatant_id"]),
                    character_slug=str(row["character_slug"] or ""),
                    display_name=str(row["display_name"] or ""),
                    initiative_bonus=int(row["initiative_bonus"] or 0),
                    dexterity_modifier=int(row["dexterity_modifier"] or 0),
                    current_hp=int(row["current_hp"] or 0),
                    max_hp=int(row["max_hp"] or 0),
                    temp_hp=int(row["temp_hp"] or 0),
                    movement_total=int(row["movement_total"] or 0),
                    movement_remaining=int(row["movement_remaining"] or 0),
                    character_state_revision=(
                        int(row["character_state_revision"])
                        if row["character_state_revision"] is not None
                        else None
                    ),
                    reconciliation_protected=bool(row["reconciliation_protected"]),
                )
                for row in rows
            )
            if any(not item.character_slug for item in database_token):
                return None
            file_token = self.character_repository.get_snapshot_source_file_token(
                campaign_slug,
                [
                    item.character_slug
                    for item in database_token
                    if item.character_state_revision is not None
                    and not item.reconciliation_protected
                ],
                previous=previous.files if previous is not None else None,
            )
            if file_token is None:
                return None
            # A policy or page revision can change effective Character numbers
            # without touching either the definition file or SQLite state.
            # Bind the skip token to the same current SourceAuthority used by
            # snapshot construction, including its source snapshot digest.
            authority_tokens: list[tuple[str, str]] = []
            for item in database_token:
                if item.character_state_revision is None or item.reconciliation_protected:
                    continue
                record = self.character_repository.get_combat_seed_character(
                    campaign_slug, item.character_slug,
                )
                if record is None or record.state_record.revision != item.character_state_revision:
                    return None
                authority = self.character_state_service.current_authority(record)
                authority_tokens.append((item.character_slug,
                                         authority.identity if authority is not None else "xianxia"))
        except Exception:
            return None

        return _PlayerCharacterSnapshotSourceToken(
            database=database_token,
            files=file_token,
            authorities=tuple(authority_tokens),
        )

    @staticmethod
    def _player_snapshot_source_token_is_cacheable(
        source_token: _PlayerCharacterSnapshotSourceToken,
        sync_result: _PlayerCharacterSnapshotFullSyncResult,
    ) -> bool:
        return all(
            item.character_state_revision is not None
            and not item.reconciliation_protected
            and item.character_slug in sync_result.loaded_character_slugs
            for item in source_token.database
        )

    def _sync_player_character_snapshots_now(
        self,
        campaign_slug: str,
        *,
        source_token: _PlayerCharacterSnapshotSourceToken | None = None,
    ) -> _PlayerCharacterSnapshotFullSyncResult:
        for attempt in range(PLAYER_SNAPSHOT_SYNC_MAX_ATTEMPTS):
            if source_token is None or attempt:
                source_token = self._read_player_character_snapshot_source_token(
                    campaign_slug,
                    previous=source_token,
                )
            if source_token is None:
                break

            try:
                pending_updates, loaded_character_slugs = self._prepare_player_snapshot_updates(
                    campaign_slug,
                    source_token=source_token,
                )
            except (OSError, TypeError, ValueError, YAMLError):
                # A source being replaced or malformed cannot authorize a
                # snapshot write. Re-read at most once, like revision drift.
                continue
            if pending_updates is None:
                continue
            if not pending_updates:
                return _PlayerCharacterSnapshotFullSyncResult(
                    changed=False,
                    loaded_character_slugs=loaded_character_slugs,
                    deferred=any(
                        item.character_state_revision is None or item.reconciliation_protected
                        for item in source_token.database
                    ),
                )

            connection = get_db()
            # Snapshot refresh owns its commit. Never consume an unrelated
            # caller's open transaction just to serve a live read.
            if connection.in_transaction:
                break
            try:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    current_source_token = self._read_player_character_snapshot_source_token(
                        campaign_slug,
                        previous=source_token,
                    )
                    if current_source_token is None or current_source_token != source_token:
                        raise CampaignCombatRevisionConflictError("Snapshot source changed.")
                    for combatant, record, snapshot, movement_remaining in pending_updates:
                        self.store.update_combatant(
                            campaign_slug,
                            combatant.id,
                            display_name=record.definition.name,
                            initiative_bonus=snapshot["initiative_bonus"],
                            dexterity_modifier=snapshot["dexterity_modifier"],
                            current_hp=snapshot["current_hp"],
                            max_hp=snapshot["max_hp"],
                            temp_hp=snapshot["temp_hp"],
                            movement_total=snapshot["movement_total"],
                            movement_remaining=movement_remaining,
                            expected_revision=combatant.revision,
                            commit=False,
                        )
                    self.store.bump_tracker_revision(campaign_slug, commit=False)
            except CampaignCombatRevisionConflictError:
                # Rebuild once from current resources and Character inputs;
                # never replay the captured movement or another stale row.
                continue
            except CampaignCombatConflictError as exc:
                raise CampaignCombatValidationError("Unable to refresh combat tracker data.") from exc
            except BaseException:
                # The instrumented context does not roll back if commit itself
                # raises. Roll back only an uncommitted transaction we own.
                if connection.in_transaction:
                    connection.rollback()
                raise
            return _PlayerCharacterSnapshotFullSyncResult(
                changed=True,
                loaded_character_slugs=loaded_character_slugs,
            )

        return _PlayerCharacterSnapshotFullSyncResult(
            changed=False,
            loaded_character_slugs=frozenset(),
            deferred=True,
        )

    def _prepare_player_snapshot_updates(
        self,
        campaign_slug: str,
        *,
        source_token: _PlayerCharacterSnapshotSourceToken,
    ) -> tuple[list[tuple[CampaignCombatantRecord, Any, dict[str, int], int]] | None, frozenset[str]]:
        source_by_id = {item.combatant_id: item for item in source_token.database}
        combatants = self.store.list_combatants(campaign_slug)
        pending_updates: list[tuple[CampaignCombatantRecord, Any, dict[str, int], int]] = []
        loaded_character_slugs: set[str] = set()
        for combatant in combatants:
            if not combatant.is_player_character or not combatant.character_slug:
                continue
            source = source_by_id.get(combatant.id)
            if source is None or source.character_slug != combatant.character_slug:
                return None, frozenset()
            if source.character_state_revision is None or source.reconciliation_protected:
                # A deleted/protected Character retains its previous encounter
                # snapshot. It is not a target in this fresh eligible batch.
                continue
            record = self.character_repository.get_combat_seed_character(
                campaign_slug,
                combatant.character_slug,
            )
            if record is None or record.state_record.revision != source.character_state_revision:
                return None, frozenset()
            loaded_character_slugs.add(combatant.character_slug)
            try:
                snapshot = self._build_player_character_snapshot(record)
            except (CampaignCombatValidationError, ValueError):
                # Keep the numeric encounter snapshot as historical table state;
                # unrelated combatants can still refresh.
                continue
            movement_remaining = min(combatant.movement_remaining, snapshot["movement_total"])
            if (
                combatant.display_name == record.definition.name
                and combatant.initiative_bonus == snapshot["initiative_bonus"]
                and combatant.dexterity_modifier == snapshot["dexterity_modifier"]
                and combatant.current_hp == snapshot["current_hp"]
                and combatant.max_hp == snapshot["max_hp"]
                and combatant.temp_hp == snapshot["temp_hp"]
                and combatant.movement_total == snapshot["movement_total"]
                and combatant.movement_remaining == movement_remaining
            ):
                continue
            pending_updates.append((combatant, record, snapshot, movement_remaining))

        return pending_updates, frozenset(loaded_character_slugs)

    def _refresh_combatant_turn_resources(
        self,
        campaign_slug: str,
        combatant_id: int,
        *,
        updated_by_user_id: int | None = None,
        commit: bool = True,
    ) -> CampaignCombatantRecord:
        combatant = self._require_combatant(campaign_slug, combatant_id)
        movement_total = combatant.movement_total
        from .committed_publication import active
        if active() and combatant.is_player_character:
            if not source_writer_reserved(get_db()) or not combatant.character_slug:
                raise CampaignCombatValidationError("Character movement source reservation is unavailable.")
            record = self._load_current_player_character(
                campaign_slug, combatant.character_slug,
            )
            if record is None:
                raise CampaignCombatValidationError("Character movement source is unavailable.")
            try:
                authority = self.character_state_service.current_authority(record)
            except ValueError as exc:
                raise CampaignCombatValidationError("Character movement source is unavailable.") from exc
            from .system_policy import is_xianxia_system
            if not is_xianxia_system(record.definition.system):
                status = authority.field_status("stats.speed") if authority is not None else None
                if (status is None or not status.is_effective
                        or MOVEMENT_VALUE_PATTERN.search(str(status.effective or "")) is None):
                    raise CampaignCombatValidationError(
                        "Movement speed needs manager repair before automatic turn refill."
                    )
                movement_total = parse_combat_movement_total(status.effective)
        return self.store.update_combatant(
            campaign_slug,
            combatant_id,
            has_action=True,
            has_bonus_action=True,
            has_reaction=True,
            movement_total=movement_total,
            movement_remaining=movement_total,
            updated_by_user_id=updated_by_user_id,
            commit=commit,
        )

    def _require_combatant(self, campaign_slug: str, combatant_id: int) -> CampaignCombatantRecord:
        combatant = self.store.get_combatant(campaign_slug, combatant_id)
        if combatant is None:
            raise CampaignCombatValidationError("That combatant could not be found.")
        return combatant

    def _load_current_player_character(self, campaign_slug: str, character_slug: str):
        try:
            return self.character_repository.get_combat_seed_character(
                campaign_slug, character_slug,
            )
        except (CharacterStateConflictError, ValueError) as exc:
            raise CampaignCombatValidationError(
                "Character source is unavailable. Refresh and retry."
            ) from exc

    def _build_player_character_snapshot(self, record) -> dict[str, int]:
        from .committed_publication import active
        seed = build_character_combat_snapshot(
            record,
            source_authority=(self.character_state_service.current_authority(record)
                              if active(get_db()) else None),
        )
        return {
            "initiative_bonus": int(seed["initiative_bonus"]),
            "dexterity_modifier": int(seed["dexterity_modifier"]),
            "current_hp": int(seed["current_hp"]),
            "max_hp": int(seed["max_hp"]),
            "temp_hp": int(seed["temp_hp"]),
            "movement_total": int(seed["movement_total"]),
        }

    def _parse_movement_total(self, value: Any | None) -> int:
        return parse_combat_movement_total(value)

    def _extract_dexterity_modifier(self, stats: dict[str, Any]) -> int:
        return extract_combat_dexterity_modifier(stats)

    def _parse_initiative_priority(self, value: Any | None, *, default: int) -> int:
        if value is None:
            return max(1, int(default or 1))
        normalized = str(value).strip()
        if not normalized:
            return 1
        try:
            parsed = int(normalized)
        except ValueError as exc:
            raise CampaignCombatValidationError("Priority must be a whole number.") from exc
        if parsed < 1:
            raise CampaignCombatValidationError("Priority must be 1 or higher.")
        return parsed

    def _normalize_resource_counter_seeds(
        self,
        seeds: list[object],
    ) -> list[NpcResourceCounterSeed]:
        return list(normalize_npc_resource_counter_seeds(seeds))

    def _normalize_resource_note_seeds(
        self,
        seeds: list[object],
    ) -> list[NpcResourceNoteSeed]:
        return list(normalize_npc_resource_note_seeds(seeds))

    def _parse_int(
        self,
        value: Any | None,
        *,
        label: str,
        default: int | None,
        minimum: int | None = 0,
    ) -> int:
        normalized = "" if value is None else str(value).strip()
        if not normalized:
            if default is None:
                raise CampaignCombatValidationError(f"{label} is required.")
            parsed = default
        else:
            try:
                parsed = int(normalized)
            except ValueError as exc:
                raise CampaignCombatValidationError(f"{label} must be a whole number.") from exc

        if minimum is not None and parsed < minimum:
            raise CampaignCombatValidationError(f"{label} cannot be less than {minimum}.")
        return parsed
