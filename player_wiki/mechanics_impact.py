from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from types import MappingProxyType
from typing import Callable, Mapping

from .source_health import (
    SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES,
    SourceHealthAccessContext,
    SourceHealthConsumer,
    SourceHealthInventoryPage,
)
from .systems_models import SystemsEntryRecord


MECHANICS_IMPACT_REVIEW_STATES = frozenset(
    {"draft", "approved", "reference_only", "manual_review"}
)
MECHANICS_IMPACT_SUPPORT_STATES = frozenset(
    {
        "modeled",
        "reference_only",
        "unsupported",
        "needs_implementation",
        "manual_review",
    }
)
MECHANICS_IMPACT_QUEUE_REVIEW_STATES = frozenset(
    {"draft", "reference_only", "manual_review"}
)
MECHANICS_IMPACT_QUEUE_SUPPORT_STATES = frozenset(
    {"reference_only", "unsupported", "needs_implementation", "manual_review"}
)
MECHANICS_IMPACT_OWNER_IDS = ("characters", "mechanics", "combat", "presets")
MECHANICS_IMPACT_QUEUE_SCAN_LIMIT = 200
MECHANICS_IMPACT_RESULT_LIMIT = 50
MECHANICS_IMPACT_PAYLOAD_LIMIT_BYTES = 65_536
MECHANICS_IMPACT_CURSOR_MAX_BYTES = 4_096
MECHANICS_IMPACT_CURSOR_TTL_SECONDS = 900


class MechanicsImpactDenied(PermissionError):
    """Non-disclosing denial for an unauthorized effective actor."""


class MechanicsImpactCursorError(ValueError):
    """Sanitized cursor validation failure."""


class MechanicsImpactInvalidMetadata(ValueError):
    """A selected row contains a non-empty state outside the frozen vocabulary."""


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


def normalize_mechanics_impact_state(value: object) -> str:
    """Apply only the vocabulary normalization approved for 10A."""

    return ("" if value is None else str(value)).strip().lower().replace("-", "_")


def _first_mechanics_impact_state(
    payload: Mapping[str, object], keys: tuple[str, ...]
) -> str:
    for key in keys:
        normalized = normalize_mechanics_impact_state(payload.get(key))
        if normalized:
            return normalized
    return ""


def mechanics_impact_statuses(
    metadata: Mapping[str, object] | None,
) -> tuple[str, str]:
    payload = dict(metadata or {})
    review = _first_mechanics_impact_state(
        payload,
        ("campaign_item_mechanics_review_status", "review_status"),
    )
    support = _first_mechanics_impact_state(
        payload,
        (
            "campaign_item_mechanics_support_state",
            "support_state",
            "xianxia_support_state",
        ),
    )
    return review, support


def validate_mechanics_impact_statuses(
    metadata: Mapping[str, object] | None,
) -> tuple[str, str]:
    review, support = mechanics_impact_statuses(metadata)
    if review and review not in MECHANICS_IMPACT_REVIEW_STATES:
        raise MechanicsImpactInvalidMetadata("Invalid mechanics review metadata.")
    if support and support not in MECHANICS_IMPACT_SUPPORT_STATES:
        raise MechanicsImpactInvalidMetadata("Invalid mechanics support metadata.")
    return review, support


def mechanics_impact_attention_rank(review: str, support: str) -> int:
    if support == "needs_implementation":
        return 0
    if support == "unsupported":
        return 1
    if review == "manual_review" or support == "manual_review":
        return 2
    if review == "draft":
        return 3
    if review == "reference_only" or support == "reference_only":
        return 4
    return 5


@dataclass(frozen=True, slots=True, order=True)
class MechanicsImpactIdentity:
    library_slug: str
    source_id: str
    entry_key: str

    @property
    def canonical_identity(self) -> str:
        return f"{self.library_slug}:{self.entry_key}"


@dataclass(frozen=True, slots=True)
class MechanicsImpactMetadataRow:
    row_id: int
    identity: MechanicsImpactIdentity
    entry_type: str
    slug: str
    metadata: Mapping[str, object]
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_value(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class MechanicsImpactQueueRow:
    identity: MechanicsImpactIdentity
    entry_type: str
    review_status: str
    support_state: str
    updated_at: str
    destination: str

    def to_payload(self) -> dict[str, object]:
        return {
            "identity": {
                "library_slug": self.identity.library_slug,
                "source_id": self.identity.source_id,
                "entry_key": self.identity.entry_key,
                "canonical": self.identity.canonical_identity,
            },
            "entry_type": self.entry_type,
            "review_status": self.review_status,
            "support_state": self.support_state,
            "updated_at": self.updated_at,
            "destination": self.destination,
        }


@dataclass(frozen=True, slots=True)
class MechanicsImpactAccessContext:
    campaign_slug: str
    system_code: str
    library_slug: str
    can_manage_systems: bool
    owner_capabilities: tuple[tuple[str, bool], ...] = ()
    can_view_private: bool = False
    source_policy_defaults: tuple[tuple[str, bool | None, str], ...] = ()

    def owner_is_authorized(self, owner_id: str) -> bool:
        return dict(self.owner_capabilities).get(owner_id, False)

    def source_health_context(self) -> SourceHealthAccessContext:
        return SourceHealthAccessContext(
            campaign_slug=self.campaign_slug,
            system_code=self.system_code,
            library_slug=self.library_slug,
            can_view_private=self.can_view_private,
            source_policy_defaults=self.source_policy_defaults,
        )


@dataclass(frozen=True, slots=True)
class MechanicsImpactQueuePage:
    rows: tuple[MechanicsImpactQueueRow, ...] = ()
    continuation: str = ""
    inspected_rows: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "rows": [row.to_payload() for row in self.rows],
            "continuation": self.continuation,
            "inspected_rows": self.inspected_rows,
            "payload_policy": {
                "cache_control": "private, no-store",
                "contains_private_data": True,
            },
        }


@dataclass(frozen=True, slots=True)
class MechanicsImpactConsumerRow:
    owner_id: str
    surface: str
    consumer_key: str
    destination: str

    def to_payload(self) -> dict[str, str]:
        return {
            "owner": self.owner_id,
            "surface": self.surface,
            "consumer_key": self.consumer_key,
            "destination": self.destination,
        }


@dataclass(frozen=True, slots=True)
class MechanicsImpactConsumerPage:
    state: str = "ready"
    rows: tuple[MechanicsImpactConsumerRow, ...] = ()
    continuation: str = ""
    complete: bool = True
    definition_file_count: int = 0
    definition_bytes: int = 0
    disclosure: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "rows": [row.to_payload() for row in self.rows],
            "continuation": self.continuation,
            "complete": self.complete,
            "measurements": {
                "definition_file_count": self.definition_file_count,
                "definition_bytes": self.definition_bytes,
            },
            "disclosure": self.disclosure,
            "payload_policy": {
                "cache_control": "private, no-store",
                "contains_private_data": True,
            },
        }


@dataclass(frozen=True, slots=True)
class MechanicsImpactPreview:
    state: str
    identity: MechanicsImpactIdentity
    entry_type: str
    input_digest: str
    current: Mapping[str, object] = field(default_factory=dict)
    proposed: Mapping[str, object] = field(default_factory=dict)
    disclosure: str = ""
    destination: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "current", _freeze_value(dict(self.current)))
        object.__setattr__(self, "proposed", _freeze_value(dict(self.proposed)))

    def to_payload(self) -> dict[str, object]:
        return {
            "state": self.state,
            "identity": {
                "library_slug": self.identity.library_slug,
                "source_id": self.identity.source_id,
                "entry_key": self.identity.entry_key,
                "canonical": self.identity.canonical_identity,
            },
            "entry_type": self.entry_type,
            "input_digest": self.input_digest,
            "current": _thaw_value(self.current),
            "proposed": _thaw_value(self.proposed),
            "disclosure": self.disclosure,
            "destination": self.destination,
            "payload_policy": {
                "cache_control": "private, no-store",
                "contains_private_data": True,
            },
        }


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.") from exc


class MechanicsImpactCursorCodec:
    _PREFIX = "mi1"

    def __init__(self, signing_key: bytes | str) -> None:
        key = signing_key.encode("utf-8") if isinstance(signing_key, str) else bytes(signing_key)
        if len(key) < 16:
            raise ValueError("Mechanics-impact cursor keys must contain at least 16 bytes.")
        self._signing_key = key

    def encode(self, payload: Mapping[str, object]) -> str:
        body = json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        signature = hmac.new(
            self._signing_key,
            self._PREFIX.encode("ascii") + b"." + body,
            sha256,
        ).digest()
        token = f"{self._PREFIX}.{_b64encode(body)}.{_b64encode(signature)}"
        if len(token.encode("ascii")) > MECHANICS_IMPACT_CURSOR_MAX_BYTES:
            raise MechanicsImpactCursorError("Mechanics-impact cursor exceeds its cap.")
        return token

    def decode(self, token: str) -> dict[str, object]:
        raw = str(token or "").strip()
        if not raw or len(raw.encode("utf-8")) > MECHANICS_IMPACT_CURSOR_MAX_BYTES:
            raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.")
        parts = raw.split(".")
        if len(parts) != 3 or parts[0] != self._PREFIX:
            raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.")
        body = _b64decode(parts[1])
        signature = _b64decode(parts[2])
        if _b64encode(body) != parts[1] or _b64encode(signature) != parts[2]:
            raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.")
        expected = hmac.new(
            self._signing_key,
            self._PREFIX.encode("ascii") + b"." + body,
            sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected):
            raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.") from exc
        if not isinstance(payload, dict):
            raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.")
        return payload


InventoryAdapter = Callable[[MechanicsImpactAccessContext, str], SourceHealthInventoryPage]


class MechanicsImpactOverlaySystemsService:
    """Request-local exact-row overlay used only by an existing projection."""

    def __init__(self, service: object, entry: SystemsEntryRecord) -> None:
        self._service = service
        self._entry = entry

    def __getattr__(self, name: str):
        return getattr(self._service, name)

    def _replace(self, candidate: object) -> object:
        if not isinstance(candidate, SystemsEntryRecord):
            return candidate
        if (
            candidate.library_slug,
            candidate.source_id,
            candidate.entry_key,
        ) == (
            self._entry.library_slug,
            self._entry.source_id,
            self._entry.entry_key,
        ):
            return self._entry
        return candidate

    def _replace_rows(self, rows: object) -> list[object]:
        return [self._replace(row) for row in list(rows or [])]

    def _enabled_source_ids(self, campaign_slug: str) -> list[str]:
        store = self._service.store
        configured = {
            row.source_id: row
            for row in store.list_campaign_enabled_sources(campaign_slug)
            if row.library_slug == self._entry.library_slug
        }
        enabled: list[str] = []
        for source in store.list_sources(self._entry.library_slug):
            policy = configured.get(source.source_id)
            is_enabled = (
                bool(policy.is_enabled)
                if policy is not None
                else bool(self._service._default_enabled_for_source(source))
            )
            if is_enabled:
                enabled.append(source.source_id)
        return enabled

    def _enabled_entry(self, campaign_slug: str, entry: object) -> object | None:
        if not isinstance(entry, SystemsEntryRecord):
            return None
        if entry.source_id not in self._enabled_source_ids(campaign_slug):
            return None
        override = self._service.store.get_campaign_entry_override(
            campaign_slug, entry.entry_key
        )
        if override is not None and override.is_enabled_override is False:
            return None
        return self._replace(entry)

    def get_campaign_library(self, _campaign_slug: str):
        return self._service.store.get_library(self._entry.library_slug)

    def get_builder_static_revision(self, *_args, **_kwargs):
        return None

    def get_entry_for_campaign(self, *args, **kwargs):
        campaign_slug = str(args[0] if args else kwargs.get("campaign_slug") or "")
        entry_key = str(args[1] if len(args) > 1 else kwargs.get("entry_key") or "").strip()
        entry = self._service.store.get_entry(self._entry.library_slug, entry_key)
        return self._enabled_entry(campaign_slug, entry)

    def get_entry_by_slug_for_campaign(self, *args, **kwargs):
        campaign_slug = str(args[0] if args else kwargs.get("campaign_slug") or "")
        entry_slug = str(
            args[1] if len(args) > 1 else kwargs.get("entry_slug") or ""
        ).strip()
        return self._enabled_entry(
            campaign_slug,
            self._service.store.get_entry_by_slug(
                self._entry.library_slug, entry_slug
            ),
        )

    def get_campaign_item_entry_by_page_ref(self, campaign_slug: str, page_ref: str):
        selected_page_ref = str(
            dict(self._entry.metadata or {}).get("linked_published_page_ref")
            or dict(self._entry.metadata or {}).get("page_ref")
            or ""
        ).strip()
        if selected_page_ref and selected_page_ref == str(page_ref or "").strip():
            return self._enabled_entry(campaign_slug, self._entry)
        return None

    def list_enabled_entries_by_identity_for_campaign(self, *args, **kwargs):
        campaign_slug = str(args[0] if args else kwargs.get("campaign_slug") or "")
        source_ids = self._enabled_source_ids(campaign_slug)
        if not source_ids:
            return []
        return self._replace_rows(
            self._service.store.list_entries_for_campaign_by_identity(
                campaign_slug,
                self._entry.library_slug,
                source_ids,
                entry_type=str(kwargs.get("entry_type") or ""),
                entry_keys=list(kwargs.get("entry_keys") or []),
                entry_slugs=list(kwargs.get("entry_slugs") or []),
                exact_titles=[],
            )
        )

    def list_enabled_entries_for_campaign(self, *args, **kwargs):
        campaign_slug = str(args[0] if args else kwargs.get("campaign_slug") or "")
        source_ids = self._enabled_source_ids(campaign_slug)
        if not source_ids:
            return []
        limit = kwargs.get("limit")
        read_limit = 10_000 if limit is None else min(max(int(limit), 1), 10_000)
        entries = self._service.store.list_entries(
            self._entry.library_slug,
            source_ids=source_ids,
            entry_type=str(kwargs.get("entry_type") or "") or None,
            limit=read_limit,
        )
        return [
            replaced
            for entry in entries
            if (replaced := self._enabled_entry(campaign_slug, entry)) is not None
        ]

    def search_entries_for_campaign(self, *args, **kwargs):
        # 10A never falls back to title/prose matching inside its overlay.
        return []


class MechanicsImpactKernel:
    """Read-only orchestration for the 10A queue, exact consumers, and previews."""

    def __init__(
        self,
        *,
        store: object,
        systems_service: object,
        authorize: Callable[[str], MechanicsImpactAccessContext | None],
        inventory_adapters: Mapping[str, InventoryAdapter],
        cursor_codec: MechanicsImpactCursorCodec,
        character_preview: Callable[
            [str, str, SystemsEntryRecord, SystemsEntryRecord], tuple[str, str]
        ]
        | None = None,
        character_authorize: Callable[[str, str], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.systems_service = systems_service
        self._authorize = authorize
        self._inventory_adapters = dict(inventory_adapters)
        if set(self._inventory_adapters) - set(MECHANICS_IMPACT_OWNER_IDS):
            raise ValueError("Unknown mechanics-impact owner adapter.")
        self._cursor_codec = cursor_codec
        self._character_preview = character_preview
        self._character_authorize = character_authorize
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _context(self, campaign_slug: str) -> MechanicsImpactAccessContext:
        requested_campaign = str(campaign_slug or "").strip()
        context = self._authorize(requested_campaign)
        if (
            context is None
            or not context.can_manage_systems
            or context.campaign_slug != requested_campaign
        ):
            raise MechanicsImpactDenied("Mechanics-impact inspection is unavailable.")
        return context

    def _decode_cursor(
        self,
        token: str,
        *,
        kind: str,
        context: MechanicsImpactAccessContext,
    ) -> dict[str, object]:
        payload = self._cursor_codec.decode(token)
        issued_at = payload.get("iat")
        if (
            payload.get("kind") != kind
            or payload.get("campaign") != context.campaign_slug
            or payload.get("library") != context.library_slug
            or type(issued_at) is not int
            or issued_at > int(self._clock().timestamp()) + 30
            or int(self._clock().timestamp()) - issued_at
            > MECHANICS_IMPACT_CURSOR_TTL_SECONDS
        ):
            raise MechanicsImpactCursorError("Stale mechanics-impact cursor.")
        return payload

    def _cursor_base(
        self,
        *,
        kind: str,
        context: MechanicsImpactAccessContext,
    ) -> dict[str, object]:
        return {
            "kind": kind,
            "campaign": context.campaign_slug,
            "library": context.library_slug,
            "iat": int(self._clock().timestamp()),
        }

    def list_queue(
        self,
        campaign_slug: str,
        *,
        continuation: str = "",
    ) -> MechanicsImpactQueuePage:
        context = self._context(campaign_slug)
        snapshot = self.store.mechanics_impact_metadata_snapshot(context.library_slug)
        after: tuple[int, str, str, int] | None = None
        if continuation:
            state = self._decode_cursor(continuation, kind="queue", context=context)
            if state.get("snapshot") != snapshot:
                raise MechanicsImpactCursorError("Stale mechanics-impact cursor.")
            raw_after = state.get("after")
            if (
                not isinstance(raw_after, list)
                or len(raw_after) != 4
                or type(raw_after[0]) is not int
                or not isinstance(raw_after[1], str)
                or not isinstance(raw_after[2], str)
                or type(raw_after[3]) is not int
            ):
                raise MechanicsImpactCursorError("Invalid mechanics-impact cursor.")
            after = (raw_after[0], raw_after[1], raw_after[2], raw_after[3])

        raw_rows, has_more = self.store.scan_mechanics_impact_metadata(
            context.library_slug,
            after=after,
            limit=MECHANICS_IMPACT_RESULT_LIMIT,
        )
        authorized_identities = (
            self.systems_service.filter_mechanics_impact_authorized_identities(
                context.source_health_context(),
                tuple(raw.identity for raw in raw_rows),
            )
            if raw_rows
            else frozenset()
        )
        queue_rows: list[MechanicsImpactQueueRow] = []
        for raw in raw_rows:
            if raw.identity not in authorized_identities:
                continue
            try:
                review, support = validate_mechanics_impact_statuses(raw.metadata)
            except MechanicsImpactInvalidMetadata:
                continue
            if (
                review not in MECHANICS_IMPACT_QUEUE_REVIEW_STATES
                and support not in MECHANICS_IMPACT_QUEUE_SUPPORT_STATES
            ):
                continue
            queue_rows.append(
                MechanicsImpactQueueRow(
                    identity=raw.identity,
                    entry_type=str(raw.entry_type or "")[:48],
                    review_status=review,
                    support_state=support,
                    updated_at=raw.updated_at.isoformat(),
                    destination=self.systems_service.mechanics_impact_destination(
                        context.campaign_slug, raw.slug
                    ),
                )
            )

        next_cursor = ""
        if has_more and raw_rows:
            last = raw_rows[-1]
            review, support = mechanics_impact_statuses(last.metadata)
            state = self._cursor_base(kind="queue", context=context)
            state.update(
                {
                    "snapshot": snapshot,
                    "after": [
                        mechanics_impact_attention_rank(review, support),
                        last.identity.source_id,
                        last.identity.entry_key,
                        last.row_id,
                    ],
                }
            )
            next_cursor = self._cursor_codec.encode(state)
        page = MechanicsImpactQueuePage(
            rows=tuple(queue_rows[:MECHANICS_IMPACT_RESULT_LIMIT]),
            continuation=next_cursor,
            inspected_rows=len(raw_rows),
        )
        if len(
            json.dumps(page.to_payload(), ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ) > MECHANICS_IMPACT_PAYLOAD_LIMIT_BYTES:
            raise ValueError("Mechanics-impact queue payload exceeds its cap.")
        return page

    def _selected_entry(
        self,
        context: MechanicsImpactAccessContext,
        identity: MechanicsImpactIdentity,
    ) -> SystemsEntryRecord:
        if identity.library_slug != context.library_slug:
            raise MechanicsImpactDenied("Mechanics-impact row is unavailable.")
        entry = self.systems_service.resolve_mechanics_impact_entry(identity)
        if entry is None:
            raise MechanicsImpactDenied("Mechanics-impact row is unavailable.")
        authorized_identities = (
            self.systems_service.filter_mechanics_impact_authorized_identities(
                context.source_health_context(),
                (identity,),
            )
        )
        if identity not in authorized_identities:
            raise MechanicsImpactDenied("Mechanics-impact row is unavailable.")
        validate_mechanics_impact_statuses(entry.metadata)
        return entry

    def list_affected_consumers(
        self,
        campaign_slug: str,
        identity: MechanicsImpactIdentity,
        *,
        owner_id: str,
        continuation: str = "",
    ) -> MechanicsImpactConsumerPage:
        context = self._context(campaign_slug)
        try:
            entry = self._selected_entry(context, identity)
        except MechanicsImpactInvalidMetadata:
            return MechanicsImpactConsumerPage(
                state="invalid_metadata",
                disclosure="The selected row has invalid mechanics review metadata.",
            )
        if owner_id not in self._inventory_adapters or not context.owner_is_authorized(
            owner_id
        ):
            return MechanicsImpactConsumerPage()

        adapter_cursor = ""
        match_offset = 0
        expected_digest = ""
        if continuation:
            state = self._decode_cursor(continuation, kind="consumer", context=context)
            if (
                state.get("owner") != owner_id
                or state.get("identity") != identity.canonical_identity
                or state.get("source") != identity.source_id
                or state.get("updated_at") != entry.updated_at.isoformat()
                or not isinstance(state.get("cursor"), str)
                or type(state.get("offset")) is not int
                or not isinstance(state.get("digest"), str)
            ):
                raise MechanicsImpactCursorError("Stale mechanics-impact cursor.")
            adapter_cursor = str(state["cursor"])
            match_offset = int(state["offset"])
            expected_digest = str(state["digest"])

        page = self._inventory_adapters[owner_id](context, adapter_cursor)
        if not isinstance(page, SourceHealthInventoryPage):
            raise ValueError("Invalid mechanics-impact owner page.")
        if (
            not 0 <= page.definition_file_count <= 50
            or not 0 <= page.definition_bytes <= SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
        ):
            raise ValueError("Invalid mechanics-impact owner measurements.")

        matches = self.systems_service.filter_mechanics_impact_consumers(
            context.source_health_context(), entry, tuple(page.consumers or ())
        )
        digest = sha256(
            json.dumps(
                [
                    [item.consumer_type, item.consumer_key, item.surface, item.destination]
                    for item in matches
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if expected_digest and expected_digest != digest:
            raise MechanicsImpactCursorError("Stale mechanics-impact cursor.")
        selected = matches[match_offset : match_offset + MECHANICS_IMPACT_RESULT_LIMIT]
        rows = tuple(
            MechanicsImpactConsumerRow(
                owner_id=owner_id,
                surface=str(item.surface or "")[:64],
                consumer_key=str(item.consumer_key or "")[:160],
                destination=self.systems_service.mechanics_impact_consumer_destination(
                    context.campaign_slug, owner_id, item.destination
                ),
            )
            for item in selected
        )
        next_cursor = ""
        next_offset = match_offset + len(selected)
        if next_offset < len(matches) or page.continuation:
            state = self._cursor_base(kind="consumer", context=context)
            if next_offset < len(matches):
                cursor_for_next = adapter_cursor
                offset_for_next = next_offset
                digest_for_next = digest
            else:
                cursor_for_next = str(page.continuation or "")
                offset_for_next = 0
                digest_for_next = ""
            state.update(
                {
                    "owner": owner_id,
                    "identity": identity.canonical_identity,
                    "source": identity.source_id,
                    "updated_at": entry.updated_at.isoformat(),
                    "cursor": cursor_for_next,
                    "offset": offset_for_next,
                    "digest": digest_for_next,
                }
            )
            next_cursor = self._cursor_codec.encode(state)
        result = MechanicsImpactConsumerPage(
            rows=rows,
            continuation=next_cursor,
            complete=not bool(next_cursor),
            definition_file_count=page.definition_file_count,
            definition_bytes=page.definition_bytes,
        )
        if len(
            json.dumps(result.to_payload(), ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ) > MECHANICS_IMPACT_PAYLOAD_LIMIT_BYTES:
            raise ValueError("Mechanics-impact consumer payload exceeds its cap.")
        return result

    def preview(
        self,
        campaign_slug: str,
        identity: MechanicsImpactIdentity,
        *,
        expected_updated_at: str,
        expected_input_digest: str,
        proposed_entry: SystemsEntryRecord,
        character_slug: str = "",
    ) -> MechanicsImpactPreview:
        context = self._context(campaign_slug)
        try:
            current = self._selected_entry(context, identity)
        except MechanicsImpactInvalidMetadata:
            unresolved = self.systems_service.resolve_mechanics_impact_entry(identity)
            if unresolved is None:
                raise MechanicsImpactDenied("Mechanics-impact row is unavailable.") from None
            return MechanicsImpactPreview(
                state="invalid_metadata",
                identity=identity,
                entry_type=str(unresolved.entry_type or "")[:48],
                input_digest="",
                disclosure="The selected row has invalid mechanics review metadata.",
                destination=self.systems_service.mechanics_impact_destination(
                    context.campaign_slug, unresolved.slug
                ),
            )
        current_digest = self.systems_service.mechanics_impact_input_digest(current)
        if (
            str(expected_updated_at or "") != current.updated_at.isoformat()
            or not hmac.compare_digest(str(expected_input_digest or ""), current_digest)
        ):
            return MechanicsImpactPreview(
                state="stale_review",
                identity=identity,
                entry_type=current.entry_type,
                input_digest=current_digest,
                disclosure="The Systems row changed. Refresh before previewing it again.",
                destination=self.systems_service.mechanics_impact_destination(
                    context.campaign_slug, current.slug
                ),
            )
        if not isinstance(proposed_entry, SystemsEntryRecord):
            raise ValueError("A normalized Systems record is required for preview.")
        proposed_identity = MechanicsImpactIdentity(
            proposed_entry.library_slug,
            proposed_entry.source_id,
            proposed_entry.entry_key,
        )
        if proposed_identity != identity or proposed_entry.entry_type != current.entry_type:
            raise ValueError("Mechanics-impact preview identity is immutable.")
        validate_mechanics_impact_statuses(proposed_entry.metadata)

        character_projection = None
        selected_character_slug = str(character_slug or "").strip()
        if selected_character_slug:
            if current.entry_type != "item":
                raise ValueError("Character projection is available only for item previews.")
            if (
                self._character_preview is None
                or self._character_authorize is None
                or not context.owner_is_authorized("characters")
                or not self._character_authorize(context.campaign_slug, selected_character_slug)
            ):
                raise MechanicsImpactDenied("Character preview is unavailable.")
            character_projection = self._character_preview(
                context.campaign_slug,
                selected_character_slug,
                current,
                proposed_entry,
            )
        payload = self.systems_service.dispatch_mechanics_impact_preview(
            current,
            proposed_entry,
            character_projection=character_projection,
        )
        return MechanicsImpactPreview(
            state=str(payload.get("state") or "preview_not_supported"),
            identity=identity,
            entry_type=current.entry_type,
            input_digest=current_digest,
            current=dict(payload.get("current") or {}),
            proposed=dict(payload.get("proposed") or {}),
            disclosure=str(payload.get("disclosure") or ""),
            destination=self.systems_service.mechanics_impact_destination(
                context.campaign_slug, current.slug
            ),
        )
