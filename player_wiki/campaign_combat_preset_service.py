from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any

from .auth_store import AuthStore
from .campaign_combat_preset_store import (
    CampaignCombatPresetConflictError,
    CampaignCombatPresetStore,
    normalize_preset_name,
)
from .campaign_combat_preset_sources import (
    CampaignCombatPresetSourceResolver,
    CampaignCombatPresetSourceValidationError,
)
from .campaign_combat_store import CampaignCombatStore
from .combat_models import (
    COMBAT_SOURCE_KIND_CHARACTER,
    COMBAT_SOURCE_KIND_DM_STATBLOCK,
    COMBAT_SOURCE_KIND_SYSTEMS_MONSTER,
)
from .combat_preset_models import (
    CampaignCombatPresetApplyReceipt,
    CampaignCombatPresetApplyReview,
    CampaignCombatPresetEntryInput,
    CampaignCombatPresetEntryRecord,
    CampaignCombatPresetMaterializedSeed,
    CampaignCombatPresetRecord,
    CampaignCombatPresetSourceInspection,
)
from .db import get_db


MAX_PRESET_ENTRIES = 50
MAX_LIST_LIMIT = 50


class CampaignCombatPresetAuthorizationError(PermissionError):
    """The effective request identity may not access the requested preset scope."""


class CampaignCombatPresetValidationError(ValueError):
    """Preset service input is invalid before persistence begins."""


class CampaignCombatPresetApplyConflictError(RuntimeError):
    """The reviewed preset application no longer matches authoritative state."""


class CampaignCombatPresetApplyOutcomeUnconfirmedError(RuntimeError):
    """The transaction committed, but its authoritative receipt was not confirmed."""


@dataclass(frozen=True, slots=True)
class CampaignCombatPresetAuthorizationContext:
    campaign_slug: str
    actor_user_id: int | None
    can_manage_combat: bool
    combat_supported: bool = True
    can_access_systems: bool = True
    can_access_dm_content: bool = True
    is_view_as: bool = False
    is_read_only: bool = False


CampaignCombatPresetAuthorizationAdapter = Callable[
    [str], CampaignCombatPresetAuthorizationContext
]


class CampaignCombatPresetService:
    def __init__(
        self,
        store: CampaignCombatPresetStore,
        auth_store: AuthStore,
        *,
        combat_store: CampaignCombatStore | None = None,
        authorization_adapter: CampaignCombatPresetAuthorizationAdapter,
        source_resolver: CampaignCombatPresetSourceResolver,
    ) -> None:
        self.store = store
        self.auth_store = auth_store
        self.combat_store = combat_store
        self._authorization_adapter = authorization_adapter
        self.source_resolver = source_resolver

    def list_presets(
        self,
        campaign_slug: str,
        *,
        limit: int = MAX_LIST_LIMIT,
        offset: int = 0,
    ) -> list[CampaignCombatPresetRecord]:
        self._authorize(campaign_slug, mutation=False)
        parsed_limit = _parse_bounded_int("limit", limit, minimum=1, maximum=MAX_LIST_LIMIT)
        parsed_offset = _parse_bounded_int("offset", offset, minimum=0)
        return self.store.list_presets(
            campaign_slug,
            limit=parsed_limit,
            offset=parsed_offset,
        )

    def get_preset(
        self,
        campaign_slug: str,
        preset_id: Any,
    ) -> CampaignCombatPresetRecord | None:
        self._authorize(campaign_slug, mutation=False)
        parsed_preset_id = _parse_bounded_int("preset_id", preset_id, minimum=1)
        return self.store.get_preset(campaign_slug, parsed_preset_id)

    def create_preset(
        self,
        campaign_slug: str,
        *,
        name: Any,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> CampaignCombatPresetRecord:
        context = self._authorize(campaign_slug, mutation=True)
        normalized_name, normalized_entries = _validate_payload(
            name,
            entries,
            allow_entry_ids=False,
        )
        self._require_source_access(context, normalized_entries)
        try:
            normalized_entries = self.source_resolver.prepare_entries_for_save(
                campaign_slug,
                normalized_entries,
            )
        except CampaignCombatPresetSourceValidationError as exc:
            raise CampaignCombatPresetValidationError(str(exc)) from exc

        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            created = self.store.create_preset(
                campaign_slug,
                name=normalized_name,
                entries=normalized_entries,
                created_by_user_id=context.actor_user_id,
                commit=False,
            )
            self.auth_store.insert_audit_event(
                event_type="campaign_encounter_preset_created",
                actor_user_id=context.actor_user_id,
                campaign_slug=campaign_slug,
                metadata={
                    "preset_id": created.id,
                    "revision": created.revision,
                    "entry_count": len(created.entries),
                },
                commit=False,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return created

    def update_preset(
        self,
        campaign_slug: str,
        preset_id: Any,
        *,
        expected_revision: Any,
        name: Any,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> CampaignCombatPresetRecord:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_preset_id = _parse_bounded_int("preset_id", preset_id, minimum=1)
        parsed_revision = _parse_bounded_int(
            "expected_revision", expected_revision, minimum=1
        )
        normalized_name, normalized_entries = _validate_payload(
            name,
            entries,
            allow_entry_ids=True,
        )
        self._require_source_access(context, normalized_entries)
        try:
            normalized_entries = self.source_resolver.prepare_entries_for_save(
                campaign_slug,
                normalized_entries,
            )
        except CampaignCombatPresetSourceValidationError as exc:
            raise CampaignCombatPresetValidationError(str(exc)) from exc

        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            updated = self.store.update_preset(
                campaign_slug,
                parsed_preset_id,
                expected_revision=parsed_revision,
                name=normalized_name,
                entries=normalized_entries,
                updated_by_user_id=context.actor_user_id,
                commit=False,
            )
            self.auth_store.insert_audit_event(
                event_type="campaign_encounter_preset_updated",
                actor_user_id=context.actor_user_id,
                campaign_slug=campaign_slug,
                metadata={
                    "preset_id": updated.id,
                    "previous_revision": parsed_revision,
                    "revision": updated.revision,
                    "entry_count": len(updated.entries),
                },
                commit=False,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return updated

    def inspect_entries(
        self,
        campaign_slug: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> tuple[CampaignCombatPresetSourceInspection, ...]:
        context = self._authorize(campaign_slug, mutation=False)
        try:
            normalized_entries = tuple(entries)
        except TypeError as exc:
            raise CampaignCombatPresetValidationError(
                "Invalid encounter preset entries."
            ) from exc
        self._require_source_access(context, normalized_entries)
        try:
            return self.source_resolver.inspect_entries(
                campaign_slug,
                normalized_entries,
            )
        except CampaignCombatPresetSourceValidationError as exc:
            raise CampaignCombatPresetValidationError(str(exc)) from exc

    def resolve_entries_for_apply(
        self,
        campaign_slug: str,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> tuple[CampaignCombatPresetMaterializedSeed, ...]:
        context = self._authorize(campaign_slug, mutation=True)
        try:
            normalized_entries = tuple(entries)
        except TypeError as exc:
            raise CampaignCombatPresetValidationError(
                "Invalid encounter preset entries."
            ) from exc
        self._require_source_access(context, normalized_entries)
        try:
            return self.source_resolver.resolve_entries_for_apply(
                campaign_slug,
                normalized_entries,
            )
        except CampaignCombatPresetSourceValidationError as exc:
            raise CampaignCombatPresetValidationError(str(exc)) from exc

    def review_preset_apply(
        self,
        campaign_slug: str,
        preset_id: Any,
    ) -> CampaignCombatPresetApplyReview:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_preset_id = _parse_bounded_int("preset_id", preset_id, minimum=1)
        return self._build_apply_review(context, campaign_slug, parsed_preset_id)

    def apply_preset(
        self,
        campaign_slug: str,
        preset_id: Any,
        *,
        confirmation_digest: Any,
    ) -> CampaignCombatPresetApplyReceipt:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_preset_id = _parse_bounded_int("preset_id", preset_id, minimum=1)
        parsed_digest = _parse_confirmation_digest(confirmation_digest)
        combat_store = self._require_combat_store()
        connection = get_db()
        created_ids: list[int] = []
        expected_operations: tuple[CampaignCombatPresetMaterializedSeed, ...] = ()
        preset: CampaignCombatPresetRecord | None = None
        tracker_revision = 0
        try:
            connection.execute("BEGIN IMMEDIATE")
            review = self._build_apply_review(context, campaign_slug, parsed_preset_id)
            if not hmac.compare_digest(parsed_digest, review.confirmation_digest):
                raise CampaignCombatPresetApplyConflictError(
                    "The saved encounter or tracker changed after review."
                )
            preset = review.preset
            expected_operations = review.operations
            combat_store.ensure_tracker(
                campaign_slug,
                updated_by_user_id=context.actor_user_id,
                commit=False,
            )
            for operation in expected_operations:
                is_character = operation.source_kind == COMBAT_SOURCE_KIND_CHARACTER
                combatant = combat_store.create_combatant(
                    campaign_slug,
                    combatant_type="player_character" if is_character else "npc",
                    character_slug=operation.source_ref if is_character else None,
                    player_detail_visible=is_character,
                    source_kind=operation.source_kind,
                    source_ref=operation.source_ref,
                    display_name=operation.display_name,
                    turn_value=operation.turn_value,
                    initiative_bonus=operation.initiative_bonus,
                    dexterity_modifier=operation.dexterity_modifier,
                    initiative_priority=operation.initiative_priority,
                    current_hp=operation.current_hp,
                    max_hp=operation.max_hp,
                    temp_hp=operation.temp_hp,
                    movement_total=operation.movement_total,
                    movement_remaining=operation.movement_total,
                    created_by_user_id=context.actor_user_id,
                    commit=False,
                )
                created_ids.append(combatant.id)
                combat_store.create_resource_counters(
                    combatant.id,
                    list(operation.resource_counter_seeds),
                    created_by_user_id=context.actor_user_id,
                    commit=False,
                )
                combat_store.create_resource_notes(
                    combatant.id,
                    list(operation.resource_note_seeds),
                    created_by_user_id=context.actor_user_id,
                    commit=False,
                )
            tracker = combat_store.bump_tracker_revision(
                campaign_slug,
                updated_by_user_id=context.actor_user_id,
                commit=False,
            )
            tracker_revision = tracker.revision
            counter_count = sum(
                len(operation.resource_counter_seeds)
                for operation in expected_operations
            )
            note_count = sum(
                len(operation.resource_note_seeds)
                for operation in expected_operations
            )
            self.auth_store.insert_audit_event(
                event_type="campaign_encounter_preset_applied",
                actor_user_id=context.actor_user_id,
                campaign_slug=campaign_slug,
                metadata={
                    "preset_id": preset.id,
                    "preset_revision": preset.revision,
                    "combatant_count": len(created_ids),
                    "counter_count": counter_count,
                    "note_count": note_count,
                    "tracker_revision": tracker_revision,
                },
                commit=False,
            )
            try:
                connection.commit()
            except BaseException as exc:
                if connection.in_transaction:
                    connection.rollback()
                    raise
                raise CampaignCombatPresetApplyOutcomeUnconfirmedError(
                    "The saved encounter commit completed without a confirmed acknowledgment."
                ) from exc
        except BaseException:
            connection.rollback()
            raise

        assert preset is not None
        try:
            self._verify_apply_receipt(
                campaign_slug,
                expected_operations,
                tuple(created_ids),
                tracker_revision=tracker_revision,
            )
        except BaseException as exc:
            raise CampaignCombatPresetApplyOutcomeUnconfirmedError(
                "The saved encounter was committed, but its result could not be confirmed."
            ) from exc
        return CampaignCombatPresetApplyReceipt(
            preset_id=preset.id,
            preset_revision=preset.revision,
            preset_name=preset.name,
            tracker_revision=tracker_revision,
            created_combatant_ids=tuple(created_ids),
            created_combatant_count=len(created_ids),
            created_counter_count=sum(
                len(operation.resource_counter_seeds)
                for operation in expected_operations
            ),
            created_note_count=sum(
                len(operation.resource_note_seeds)
                for operation in expected_operations
            ),
        )

    def _build_apply_review(
        self,
        context: CampaignCombatPresetAuthorizationContext,
        campaign_slug: str,
        preset_id: int,
    ) -> CampaignCombatPresetApplyReview:
        combat_store = self._require_combat_store()
        preset = self.store.get_preset(campaign_slug, preset_id)
        if preset is None:
            raise CampaignCombatPresetApplyConflictError(
                "The saved encounter is unavailable."
            )
        if not preset.entries:
            raise CampaignCombatPresetValidationError(
                "An empty saved encounter cannot be applied."
            )
        self._require_source_access(context, preset.entries)
        try:
            operations = self.source_resolver.resolve_entries_for_apply(
                campaign_slug,
                preset.entries,
            )
        except CampaignCombatPresetSourceValidationError as exc:
            raise CampaignCombatPresetValidationError(str(exc)) from exc
        if not operations:
            raise CampaignCombatPresetValidationError(
                "A saved encounter must create at least one combatant."
            )
        character_slugs = [
            operation.source_ref
            for operation in operations
            if operation.source_kind == COMBAT_SOURCE_KIND_CHARACTER
        ]
        if len(character_slugs) != len(set(character_slugs)):
            raise CampaignCombatPresetValidationError(
                "A Character may appear only once in a saved encounter apply."
            )
        existing_combatants = tuple(combat_store.list_combatants(campaign_slug))
        existing_character_slugs = {
            combatant.character_slug
            for combatant in existing_combatants
            if combatant.character_slug
        }
        if existing_character_slugs.intersection(character_slugs):
            raise CampaignCombatPresetValidationError(
                "A Character from this saved encounter is already in the tracker."
            )
        tracker = combat_store.get_tracker(campaign_slug)
        tracker_present = tracker is not None
        tracker_revision = tracker.revision if tracker is not None else 0
        digest = _apply_confirmation_digest(
            context,
            campaign_slug=campaign_slug,
            preset=preset,
            tracker_present=tracker_present,
            tracker_revision=tracker_revision,
            operations=operations,
        )
        return CampaignCombatPresetApplyReview(
            preset=preset,
            operations=operations,
            existing_combatants=existing_combatants,
            tracker_present=tracker_present,
            tracker_revision=tracker_revision,
            confirmation_digest=digest,
        )

    def _verify_apply_receipt(
        self,
        campaign_slug: str,
        operations: tuple[CampaignCombatPresetMaterializedSeed, ...],
        created_ids: tuple[int, ...],
        *,
        tracker_revision: int,
    ) -> None:
        combat_store = self._require_combat_store()
        tracker = combat_store.get_tracker(campaign_slug)
        if tracker is None or tracker.revision != tracker_revision:
            raise RuntimeError("Combat tracker receipt mismatch.")
        combatants = tuple(
            combat_store.get_combatant(campaign_slug, combatant_id)
            for combatant_id in created_ids
        )
        if any(combatant is None for combatant in combatants):
            raise RuntimeError("Combatant receipt is incomplete.")
        for operation, combatant in zip(operations, combatants, strict=True):
            assert combatant is not None
            expected_character_slug = (
                operation.source_ref
                if operation.source_kind == COMBAT_SOURCE_KIND_CHARACTER
                else None
            )
            actual = (
                combatant.combatant_type,
                combatant.character_slug,
                combatant.player_detail_visible,
                combatant.source_kind,
                combatant.source_ref,
                combatant.display_name,
                combatant.turn_value,
                combatant.initiative_bonus,
                combatant.dexterity_modifier,
                combatant.initiative_priority,
                combatant.current_hp,
                combatant.max_hp,
                combatant.temp_hp,
                combatant.movement_total,
                combatant.movement_remaining,
            )
            expected = (
                "player_character"
                if operation.source_kind == COMBAT_SOURCE_KIND_CHARACTER
                else "npc",
                expected_character_slug,
                operation.source_kind == COMBAT_SOURCE_KIND_CHARACTER,
                operation.source_kind,
                operation.source_ref,
                operation.display_name,
                operation.turn_value,
                operation.initiative_bonus,
                operation.dexterity_modifier,
                operation.initiative_priority,
                operation.current_hp,
                operation.max_hp,
                operation.temp_hp,
                operation.movement_total,
                operation.movement_total,
            )
            if actual != expected:
                raise RuntimeError("Combatant receipt mismatch.")
        counters = combat_store.list_resource_counters(
            campaign_slug,
            combatant_ids=list(created_ids),
        )
        notes = combat_store.list_resource_notes(
            campaign_slug,
            combatant_ids=list(created_ids),
        )
        counter_projection = [
            (
                counter.combatant_id,
                counter.resource_key,
                counter.label,
                counter.current_value,
                counter.max_value,
                counter.reset_label,
                counter.source_label,
            )
            for counter in counters
        ]
        expected_counter_projection = [
            (
                combatant_id,
                seed.resource_key,
                seed.label,
                seed.current_value,
                seed.max_value,
                seed.reset_label,
                seed.source_label,
            )
            for combatant_id, operation in zip(created_ids, operations, strict=True)
            for seed in operation.resource_counter_seeds
        ]
        note_projection = [
            (note.combatant_id, note.label, note.note, note.source_label)
            for note in notes
        ]
        expected_note_projection = [
            (combatant_id, seed.label, seed.note, seed.source_label)
            for combatant_id, operation in zip(created_ids, operations, strict=True)
            for seed in operation.resource_note_seeds
        ]
        if counter_projection != expected_counter_projection:
            raise RuntimeError("Counter receipt mismatch.")
        if note_projection != expected_note_projection:
            raise RuntimeError("Note receipt mismatch.")

    def _require_combat_store(self) -> CampaignCombatStore:
        if self.combat_store is None:
            raise RuntimeError("Combat preset apply storage is unavailable.")
        return self.combat_store

    def delete_preset(
        self,
        campaign_slug: str,
        preset_id: Any,
        *,
        expected_revision: Any,
    ) -> None:
        context = self._authorize(campaign_slug, mutation=True)
        parsed_preset_id = _parse_bounded_int("preset_id", preset_id, minimum=1)
        parsed_revision = _parse_bounded_int(
            "expected_revision", expected_revision, minimum=1
        )

        connection = get_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = self.store.get_preset(campaign_slug, parsed_preset_id)
            if existing is None or existing.revision != parsed_revision:
                raise CampaignCombatPresetConflictError(
                    "Unable to delete encounter preset."
                )
            self.store.delete_preset(
                campaign_slug,
                parsed_preset_id,
                expected_revision=parsed_revision,
                commit=False,
            )
            self.auth_store.insert_audit_event(
                event_type="campaign_encounter_preset_deleted",
                actor_user_id=context.actor_user_id,
                campaign_slug=campaign_slug,
                metadata={
                    "preset_id": parsed_preset_id,
                    "revision": parsed_revision,
                    "entry_count": len(existing.entries),
                },
                commit=False,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    def _authorize(
        self,
        campaign_slug: str,
        *,
        mutation: bool,
    ) -> CampaignCombatPresetAuthorizationContext:
        context = self._authorization_adapter(campaign_slug)
        if (
            not isinstance(context, CampaignCombatPresetAuthorizationContext)
            or context.campaign_slug != campaign_slug
            or not context.can_manage_combat
            or not context.combat_supported
        ):
            raise CampaignCombatPresetAuthorizationError(
                "Encounter preset access is not authorized."
            )
        if mutation and (context.is_view_as or context.is_read_only):
            raise CampaignCombatPresetAuthorizationError(
                "Encounter preset changes are unavailable in read-only mode."
            )
        if mutation and context.actor_user_id is None:
            raise CampaignCombatPresetAuthorizationError(
                "Encounter preset changes require an authenticated actor."
            )
        return context

    @staticmethod
    def _require_source_access(
        context: CampaignCombatPresetAuthorizationContext,
        entries: Sequence[
            CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
        ],
    ) -> None:
        source_kinds = {
            str(getattr(entry, "source_kind", "") or "")
            for entry in entries
        }
        if (
            COMBAT_SOURCE_KIND_SYSTEMS_MONSTER in source_kinds
            and not context.can_access_systems
        ):
            raise CampaignCombatPresetAuthorizationError(
                "Encounter preset source access is not authorized."
            )
        if (
            COMBAT_SOURCE_KIND_DM_STATBLOCK in source_kinds
            and not context.can_access_dm_content
        ):
            raise CampaignCombatPresetAuthorizationError(
                "Encounter preset source access is not authorized."
            )


def _parse_bounded_int(
    field_name: str,
    value: Any,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise CampaignCombatPresetValidationError(f"Invalid {field_name}.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized or not normalized.lstrip("+-").isdecimal():
            raise CampaignCombatPresetValidationError(f"Invalid {field_name}.")
        parsed = int(normalized)
    else:
        raise CampaignCombatPresetValidationError(f"Invalid {field_name}.")
    if parsed < minimum or (maximum is not None and parsed > maximum):
        raise CampaignCombatPresetValidationError(f"Invalid {field_name}.")
    return parsed


def _validate_payload(
    name: Any,
    entries: Sequence[
        CampaignCombatPresetEntryInput | CampaignCombatPresetEntryRecord
    ],
    *,
    allow_entry_ids: bool,
) -> tuple[str, tuple[CampaignCombatPresetEntryInput, ...]]:
    try:
        normalized_name, name_key = normalize_preset_name(name)
    except (TypeError, ValueError) as exc:
        raise CampaignCombatPresetValidationError("Invalid encounter preset name.") from exc
    if (
        not normalized_name
        or len(normalized_name.encode("utf-8")) > 320
        or len(name_key.encode("utf-8")) > 512
    ):
        raise CampaignCombatPresetValidationError("Invalid encounter preset name.")

    try:
        raw_entries = tuple(entries)
    except TypeError as exc:
        raise CampaignCombatPresetValidationError("Invalid encounter preset entries.") from exc
    if len(raw_entries) > MAX_PRESET_ENTRIES:
        raise CampaignCombatPresetValidationError(
            f"Encounter presets may contain at most {MAX_PRESET_ENTRIES} entries."
        )

    normalized_entries: list[CampaignCombatPresetEntryInput] = []
    for entry in raw_entries:
        if isinstance(entry, CampaignCombatPresetEntryRecord):
            entry = entry.as_input()
        if not isinstance(entry, CampaignCombatPresetEntryInput):
            raise CampaignCombatPresetValidationError("Invalid encounter preset entry.")
        if entry.id is not None:
            parsed_entry_id = _parse_bounded_int("entry id", entry.id, minimum=1)
            if not allow_entry_ids or parsed_entry_id != entry.id:
                raise CampaignCombatPresetValidationError(
                    "Invalid encounter preset entry ID."
                )
        normalized_entries.append(entry)
    retained_ids = [entry.id for entry in normalized_entries if entry.id is not None]
    if len(retained_ids) != len(set(retained_ids)):
        raise CampaignCombatPresetValidationError("Duplicate encounter preset entry ID.")
    return normalized_name, tuple(normalized_entries)


def _parse_confirmation_digest(value: Any) -> str:
    if not isinstance(value, str):
        raise CampaignCombatPresetValidationError("Invalid apply confirmation.")
    normalized = value.strip()
    if (
        len(normalized) != 64
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise CampaignCombatPresetValidationError("Invalid apply confirmation.")
    return normalized


def _apply_confirmation_digest(
    context: CampaignCombatPresetAuthorizationContext,
    *,
    campaign_slug: str,
    preset: CampaignCombatPresetRecord,
    tracker_present: bool,
    tracker_revision: int,
    operations: tuple[CampaignCombatPresetMaterializedSeed, ...],
) -> str:
    payload = {
        "version": "encounter-preset-apply-v1",
        "authorization": {
            "actor_user_id": context.actor_user_id,
            "can_manage_combat": context.can_manage_combat,
            "can_access_systems": context.can_access_systems,
            "can_access_dm_content": context.can_access_dm_content,
            "combat_supported": context.combat_supported,
            "is_view_as": context.is_view_as,
            "is_read_only": context.is_read_only,
        },
        "campaign_slug": campaign_slug,
        "preset": {"id": preset.id, "revision": preset.revision},
        "tracker": {
            "present": tracker_present,
            "revision": tracker_revision,
        },
        "operations": [
            {
                "entry_id": operation.entry_id,
                "position": operation.position,
                "quantity_index": operation.quantity_index,
                "source_kind": operation.source_kind,
                "source_ref": operation.source_ref,
                "source_version": operation.source_version,
                "version_scheme": operation.version_scheme,
                "display_name": operation.display_name,
                "turn_value": operation.turn_value,
                "initiative_bonus": operation.initiative_bonus,
                "dexterity_modifier": operation.dexterity_modifier,
                "initiative_priority": operation.initiative_priority,
                "current_hp": operation.current_hp,
                "max_hp": operation.max_hp,
                "temp_hp": operation.temp_hp,
                "movement_total": operation.movement_total,
                "counters": [
                    {
                        "resource_key": seed.resource_key,
                        "label": seed.label,
                        "current_value": seed.current_value,
                        "max_value": seed.max_value,
                        "reset_label": seed.reset_label,
                        "source_label": seed.source_label,
                    }
                    for seed in operation.resource_counter_seeds
                ],
                "notes": [
                    {
                        "label": seed.label,
                        "note": seed.note,
                        "source_label": seed.source_label,
                    }
                    for seed in operation.resource_note_seeds
                ],
            }
            for operation in operations
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
