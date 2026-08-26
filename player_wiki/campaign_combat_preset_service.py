from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .auth_store import AuthStore
from .campaign_combat_preset_store import (
    CampaignCombatPresetConflictError,
    CampaignCombatPresetStore,
    normalize_preset_name,
)
from .combat_preset_models import (
    CampaignCombatPresetEntryInput,
    CampaignCombatPresetEntryRecord,
    CampaignCombatPresetRecord,
)
from .db import get_db


MAX_PRESET_ENTRIES = 50
MAX_LIST_LIMIT = 50


class CampaignCombatPresetAuthorizationError(PermissionError):
    """The effective request identity may not access the requested preset scope."""


class CampaignCombatPresetValidationError(ValueError):
    """Preset service input is invalid before persistence begins."""


@dataclass(frozen=True, slots=True)
class CampaignCombatPresetAuthorizationContext:
    campaign_slug: str
    actor_user_id: int | None
    can_manage_combat: bool
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
        authorization_adapter: CampaignCombatPresetAuthorizationAdapter,
    ) -> None:
        self.store = store
        self.auth_store = auth_store
        self._authorization_adapter = authorization_adapter

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
