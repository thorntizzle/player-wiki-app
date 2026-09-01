from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import unquote_to_bytes, urlencode, urlsplit

from flask import url_for

from .mechanics_impact import (
    MECHANICS_IMPACT_OWNER_IDS,
    MechanicsImpactAccessContext,
    MechanicsImpactCursorError,
    MechanicsImpactIdentity,
    MechanicsImpactKernel,
    MechanicsImpactQueuePage,
    MechanicsImpactReview,
    MechanicsImpactStale,
)
from .systems_labels import SYSTEMS_ENTRY_TYPE_LABELS


MECHANICS_IMPACT_BROWSER_REQUEST_TARGET_MAX_BYTES = 4_096
MECHANICS_IMPACT_BROWSER_TOKEN_MAX_BYTES = 3_840
MECHANICS_IMPACT_BROWSER_SUCCESS_MAX_BYTES = 131_072
MECHANICS_IMPACT_BROWSER_ERROR_MAX_BYTES = 65_536

MECHANICS_IMPACT_BROWSER_ERROR_MESSAGE = (
    "The mechanics review request could not be completed. Use a fresh review link."
)
MECHANICS_IMPACT_BROWSER_STALE_MESSAGE = (
    "This mechanics review is no longer current. Return to the queue and refresh it."
)

_OWNER_LABELS = {
    "characters": "Characters and equipment",
    "mechanics": "Published Mechanics",
    "combat": "Combat",
    "presets": "Combat presets",
}

_STATUS_LABELS = {
    "": "Not recorded",
    "approved": "Approved",
    "draft": "Draft",
    "manual_review": "Manual review",
    "modeled": "Modeled",
    "needs_implementation": "Needs implementation",
    "reference_only": "Reference only",
    "unsupported": "Unsupported",
}


@dataclass(frozen=True, slots=True)
class MechanicsImpactBrowserQuery:
    continuation: str = ""
    selection: str = ""
    owner: str = ""
    owner_continuation: str = ""
    queue_return: str = ""
    preview: str = ""
    character: str = ""


def _decode_component(value: bytes) -> str:
    index = 0
    while index < len(value):
        if value[index] == ord("%"):
            if (
                index + 2 >= len(value)
                or value[index + 1] not in b"0123456789abcdefABCDEF"
                or value[index + 2] not in b"0123456789abcdefABCDEF"
            ):
                raise MechanicsImpactCursorError(
                    "Invalid mechanics-impact query encoding."
                )
            index += 3
            continue
        index += 1
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MechanicsImpactCursorError(
            "Invalid mechanics-impact query encoding."
        ) from exc


def _strict_pairs(path: str, raw_query: bytes) -> tuple[tuple[str, str], ...]:
    target_bytes = len(str(path or "").encode("utf-8")) + (
        1 + len(raw_query) if raw_query else 0
    )
    if target_bytes > MECHANICS_IMPACT_BROWSER_REQUEST_TARGET_MAX_BYTES:
        raise MechanicsImpactCursorError(
            "Mechanics-impact request target exceeds its cap."
        )
    if not raw_query:
        return ()

    pairs: list[tuple[str, str]] = []
    keys: set[str] = set()
    for segment in raw_query.split(b"&"):
        if not segment or segment.count(b"=") != 1:
            raise MechanicsImpactCursorError(
                "Invalid mechanics-impact query grammar."
            )
        raw_key, raw_value = segment.split(b"=", 1)
        key = _decode_component(raw_key)
        value = _decode_component(raw_value)
        if not key or not value.strip() or key in keys:
            raise MechanicsImpactCursorError(
                "Invalid mechanics-impact query grammar."
            )
        if key in {
            "continuation",
            "selection",
            "owner_continuation",
            "queue_return",
            "preview",
        } and len(value.encode("utf-8")) > MECHANICS_IMPACT_BROWSER_TOKEN_MAX_BYTES:
            raise MechanicsImpactCursorError(
                "Mechanics-impact browser token exceeds its cap."
            )
        keys.add(key)
        pairs.append((key, value))
    return tuple(pairs)


def parse_mechanics_impact_queue_query(
    path: str,
    raw_query: bytes,
) -> MechanicsImpactBrowserQuery:
    pairs = _strict_pairs(path, raw_query)
    if not pairs:
        return MechanicsImpactBrowserQuery()
    if len(pairs) != 1 or pairs[0][0] != "continuation":
        raise MechanicsImpactCursorError("Invalid mechanics-impact queue query.")
    return MechanicsImpactBrowserQuery(continuation=pairs[0][1])


def parse_mechanics_impact_detail_query(
    path: str,
    raw_query: bytes,
) -> MechanicsImpactBrowserQuery:
    pairs = _strict_pairs(path, raw_query)
    values = dict(pairs)
    keys = set(values)
    if "preview" in keys or "character" in keys:
        allowed = {"preview", "character", "queue_return"}
        if keys - allowed or not {"preview", "character"} <= keys:
            raise MechanicsImpactCursorError(
                "Invalid mechanics-impact preview query."
            )
        return MechanicsImpactBrowserQuery(
            preview=values["preview"],
            character=values["character"],
            queue_return=values.get("queue_return", ""),
        )

    allowed = {"selection", "owner", "owner_continuation", "queue_return"}
    if keys - allowed or "selection" not in keys:
        raise MechanicsImpactCursorError("Invalid mechanics-impact detail query.")
    owner = values.get("owner", "")
    if owner and owner not in MECHANICS_IMPACT_OWNER_IDS:
        raise MechanicsImpactCursorError("Unknown mechanics-impact owner.")
    if "owner_continuation" in keys and not owner:
        raise MechanicsImpactCursorError(
            "Mechanics-impact owner continuation requires an owner."
        )
    return MechanicsImpactBrowserQuery(
        selection=values["selection"],
        owner=owner,
        owner_continuation=values.get("owner_continuation", ""),
        queue_return=values.get("queue_return", ""),
    )


def _status_label(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return _STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def _humanize(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized.replace("_", " ").replace("-", " ").title()


def _identity_claims(identity: MechanicsImpactIdentity) -> dict[str, object]:
    return {
        "source": identity.source_id,
        "entry": identity.entry_key,
    }


def _identity_from_state(
    state: Mapping[str, object],
    context: MechanicsImpactAccessContext,
) -> MechanicsImpactIdentity:
    source_id = state.get("source")
    entry_key = state.get("entry")
    if (
        not isinstance(source_id, str)
        or not source_id.strip()
        or len(source_id) > 96
        or not isinstance(entry_key, str)
        or not entry_key.strip()
        or len(entry_key) > 512
    ):
        raise MechanicsImpactCursorError("Invalid mechanics-impact browser state.")
    return MechanicsImpactIdentity(
        context.library_slug,
        source_id,
        entry_key,
    )


class MechanicsImpactPresenter:
    """Allowlist-only browser presentation over the read-only 10A kernel."""

    def __init__(self, kernel: MechanicsImpactKernel) -> None:
        self.kernel = kernel

    def access_context(self, campaign_slug: str) -> MechanicsImpactAccessContext:
        return self.kernel.access_context(campaign_slug)

    def _encode(
        self,
        context: MechanicsImpactAccessContext,
        *,
        purpose: str,
        claims: Mapping[str, object],
    ) -> str:
        token = self.kernel.encode_browser_state(
            context,
            purpose=purpose,
            claims=claims,
        )
        if len(token.encode("ascii")) > MECHANICS_IMPACT_BROWSER_TOKEN_MAX_BYTES:
            raise MechanicsImpactCursorError(
                "Mechanics-impact browser token exceeds its cap."
            )
        return token

    def _decode(
        self,
        context: MechanicsImpactAccessContext,
        token: str,
        *,
        purpose: str,
    ) -> dict[str, object]:
        if len(str(token or "").encode("utf-8")) > MECHANICS_IMPACT_BROWSER_TOKEN_MAX_BYTES:
            raise MechanicsImpactCursorError(
                "Mechanics-impact browser token exceeds its cap."
            )
        return self.kernel.decode_browser_state(
            context,
            token,
            purpose=purpose,
        )

    @staticmethod
    def _detail_url(campaign_slug: str, pairs: tuple[tuple[str, str], ...]) -> str:
        base = url_for(
            "campaign_systems_mechanics_impact_detail",
            campaign_slug=campaign_slug,
        )
        return f"{base}?{urlencode(pairs)}"

    @staticmethod
    def _queue_url(campaign_slug: str, continuation: str = "") -> str:
        base = url_for(
            "campaign_systems_mechanics_impact_queue",
            campaign_slug=campaign_slug,
        )
        return (
            f"{base}?{urlencode((('continuation', continuation),))}"
            if continuation
            else base
        )

    def present_queue(
        self,
        context: MechanicsImpactAccessContext,
        page: MechanicsImpactQueuePage,
        *,
        incoming_continuation: str = "",
    ) -> dict[str, object]:
        queue_return = self._encode(
            context,
            purpose="queue-return",
            claims={
                "snapshot": page.snapshot,
                "continuation": incoming_continuation,
            },
        )
        rows: list[dict[str, object]] = []
        for row in page.rows:
            selection = self._encode(
                context,
                purpose="selection",
                claims={
                    **_identity_claims(row.identity),
                    "updated_at": row.updated_at,
                    "snapshot": page.snapshot,
                },
            )
            detail_url = self._detail_url(
                context.campaign_slug,
                (
                    ("selection", selection),
                    ("queue_return", queue_return),
                ),
            )
            rows.append(
                {
                    "entry_type": SYSTEMS_ENTRY_TYPE_LABELS.get(
                        row.entry_type,
                        _humanize(row.entry_type),
                    ),
                    "review_status": _status_label(row.review_status),
                    "support_state": _status_label(row.support_state),
                    "source_id": row.identity.source_id,
                    "entry_key": row.identity.entry_key,
                    "canonical_identity": row.identity.canonical_identity,
                    "updated_at": row.updated_at,
                    "detail_url": detail_url,
                    "entry_url": row.destination,
                }
            )
        return {
            "state": "ready",
            "rows": rows,
            "has_more": bool(page.continuation),
            "next_url": self._queue_url(
                context.campaign_slug,
                page.continuation,
            )
            if page.continuation
            else "",
            "page_complete": not bool(page.continuation),
        }

    def _decode_queue_return(
        self,
        context: MechanicsImpactAccessContext,
        token: str,
        *,
        expected_snapshot: str,
    ) -> str:
        if not token:
            return self._queue_url(context.campaign_slug)
        state = self._decode(context, token, purpose="queue-return")
        continuation = state.get("continuation")
        if (
            state.get("snapshot") != expected_snapshot
            or not isinstance(continuation, str)
        ):
            raise MechanicsImpactStale("Stale mechanics-impact queue return.")
        return self._queue_url(context.campaign_slug, continuation)

    def _selection_state(
        self,
        context: MechanicsImpactAccessContext,
        query: MechanicsImpactBrowserQuery,
    ) -> tuple[MechanicsImpactIdentity, str, str, str, str]:
        if query.preview:
            state = self._decode(context, query.preview, purpose="preview")
            character = state.get("character")
            digest = state.get("digest")
            if (
                not isinstance(character, str)
                or character != query.character
                or not isinstance(digest, str)
                or len(digest) != 64
            ):
                raise MechanicsImpactStale("Stale mechanics-impact preview.")
        else:
            state = self._decode(context, query.selection, purpose="selection")
            character = ""
            digest = ""
        updated_at = state.get("updated_at")
        snapshot = state.get("snapshot")
        if not isinstance(updated_at, str) or not isinstance(snapshot, str):
            raise MechanicsImpactCursorError("Invalid mechanics-impact browser state.")
        return (
            _identity_from_state(state, context),
            updated_at,
            snapshot,
            digest,
            character,
        )

    def load_review(
        self,
        context: MechanicsImpactAccessContext,
        query: MechanicsImpactBrowserQuery,
    ) -> MechanicsImpactReview:
        identity, updated_at, snapshot, digest, character = self._selection_state(
            context,
            query,
        )
        return self.kernel.review(
            context,
            identity,
            expected_updated_at=updated_at,
            expected_input_digest=digest,
            expected_snapshot=snapshot,
            owner_id=query.owner,
            continuation=query.owner_continuation,
            character_slug=character,
        )

    @staticmethod
    def _character_slug(
        campaign_slug: str,
        consumer_key: str,
        destination: str,
    ) -> str:
        parsed = urlsplit(destination)
        prefix = f"/campaigns/{campaign_slug}/characters/"
        if parsed.query or parsed.fragment or not parsed.path.startswith(prefix):
            return ""
        character_slug = parsed.path[len(prefix) :]
        if (
            not character_slug
            or "/" in character_slug
            or not str(consumer_key or "").startswith(f"{character_slug}:")
        ):
            return ""
        return character_slug

    def present_review(
        self,
        context: MechanicsImpactAccessContext,
        review: MechanicsImpactReview,
        query: MechanicsImpactBrowserQuery,
        *,
        can_edit_shared: bool,
        can_manage_dm_content: bool,
        custom_source_id: str,
    ) -> dict[str, object]:
        queue_url = self._decode_queue_return(
            context,
            query.queue_return,
            expected_snapshot=review.snapshot,
        )
        selection = self._encode(
            context,
            purpose="selection",
            claims={
                **_identity_claims(review.row.identity),
                "updated_at": review.row.updated_at,
                "snapshot": review.snapshot,
            },
        )
        queue_return = query.queue_return
        owner_links = []
        for owner_id in MECHANICS_IMPACT_OWNER_IDS:
            if not context.owner_is_authorized(owner_id):
                continue
            pairs = [("selection", selection), ("owner", owner_id)]
            if queue_return:
                pairs.append(("queue_return", queue_return))
            owner_links.append(
                {
                    "owner_id": owner_id,
                    "label": _OWNER_LABELS[owner_id],
                    "url": self._detail_url(context.campaign_slug, tuple(pairs)),
                    "selected": owner_id == review.owner_id,
                }
            )

        consumer_rows = []
        for row in review.consumers.rows:
            preview_url = ""
            if row.owner_id == "characters" and review.row.entry_type == "item":
                character_slug = self._character_slug(
                    context.campaign_slug,
                    row.consumer_key,
                    row.destination,
                )
                if character_slug:
                    preview_token = self._encode(
                        context,
                        purpose="preview",
                        claims={
                            **_identity_claims(review.row.identity),
                            "updated_at": review.row.updated_at,
                            "snapshot": review.snapshot,
                            "digest": review.input_digest,
                            "character": character_slug,
                        },
                    )
                    pairs = [
                        ("preview", preview_token),
                        ("character", character_slug),
                    ]
                    if queue_return:
                        pairs.append(("queue_return", queue_return))
                    preview_url = self._detail_url(
                        context.campaign_slug,
                        tuple(pairs),
                    )
            consumer_rows.append(
                {
                    "surface": str(row.surface or "")[:64],
                    "consumer_key": str(row.consumer_key or "")[:160],
                    "destination": row.destination,
                    "preview_url": preview_url,
                }
            )

        next_owner_url = ""
        if review.consumers.continuation and review.owner_id:
            pairs = [
                ("selection", selection),
                ("owner", review.owner_id),
                ("owner_continuation", review.consumers.continuation),
            ]
            if queue_return:
                pairs.append(("queue_return", queue_return))
            next_owner_url = self._detail_url(
                context.campaign_slug,
                tuple(pairs),
            )

        entry_slug = review.row.destination.rsplit("/", 1)[-1]
        editor_actions: list[dict[str, str]] = []
        if not review.invalid_metadata:
            if review.row.identity.source_id == custom_source_id:
                editor_actions.append(
                    {
                        "label": "Edit custom entry",
                        "url": url_for(
                            "campaign_systems_control_panel_edit_custom_entry",
                            campaign_slug=context.campaign_slug,
                            entry_slug=entry_slug,
                            return_to="dm-content-systems",
                            _anchor="systems-custom-entry-editor",
                        ),
                    }
                )
            else:
                if can_edit_shared:
                    editor_actions.append(
                        {
                            "label": "Edit shared/core entry",
                            "url": url_for(
                                "campaign_systems_control_panel_edit_shared_entry",
                                campaign_slug=context.campaign_slug,
                                entry_slug=entry_slug,
                            ),
                        }
                    )
                if can_manage_dm_content:
                    editor_actions.append(
                        {
                            "label": "Manage campaign override",
                            "url": url_for(
                                "campaign_dm_content_subpage_view",
                                campaign_slug=context.campaign_slug,
                                dm_content_subpage="systems",
                                entry_key=review.row.identity.entry_key,
                                _anchor="systems-entry-overrides",
                            ),
                        }
                    )

        preview = self._present_preview(review)
        return {
            "state": "invalid_metadata" if review.invalid_metadata else "ready",
            "entry_type": SYSTEMS_ENTRY_TYPE_LABELS.get(
                review.row.entry_type,
                _humanize(review.row.entry_type),
            ),
            "review_status": _status_label(review.row.review_status),
            "support_state": _status_label(review.row.support_state),
            "source_id": review.row.identity.source_id,
            "entry_key": review.row.identity.entry_key,
            "canonical_identity": review.row.identity.canonical_identity,
            "updated_at": review.row.updated_at,
            "entry_url": review.row.destination,
            "queue_url": queue_url,
            "owner_links": owner_links,
            "selected_owner_label": _OWNER_LABELS.get(review.owner_id, ""),
            "owner_authorized": review.owner_authorized,
            "consumer_rows": consumer_rows,
            "owner_incomplete": bool(review.consumers.continuation),
            "next_owner_url": next_owner_url,
            "preview": preview,
            "editor_actions": editor_actions,
            "invalid_message": (
                "This row has invalid mechanics review metadata. Consumer and preview "
                "inspection are unavailable until the Systems entry is corrected."
                if review.invalid_metadata
                else ""
            ),
        }

    @staticmethod
    def _present_preview(review: MechanicsImpactReview) -> dict[str, object]:
        preview = review.preview
        if preview is None:
            return {"state": "preview_not_supported", "rows": []}
        if preview.state in {"invalid_metadata", "stale_review"}:
            return {
                "state": preview.state,
                "state_label": _humanize(preview.state),
                "disclosure": preview.disclosure,
                "rows": [],
            }
        if preview.state == "preview_not_supported":
            return {
                "state": preview.state,
                "state_label": "Preview not supported",
                "disclosure": preview.disclosure,
                "rows": [],
            }

        if review.row.entry_type == "item":
            current = dict(preview.current)
            proposed = dict(preview.proposed)
            current_fields = [
                _humanize(value)
                for value in list(current.get("activated_modeled_fields") or ())
            ]
            proposed_fields = [
                _humanize(value)
                for value in list(proposed.get("activated_modeled_fields") or ())
            ]
            current_flags = [
                _humanize(value)
                for value in list(current.get("review_flag_codes") or ())
            ]
            proposed_flags = [
                _humanize(value)
                for value in list(proposed.get("review_flag_codes") or ())
            ]
            rows: list[dict[str, str]] = [
                {
                    "label": "Review status",
                    "current": _status_label(current.get("review_status")),
                    "proposed": _status_label(proposed.get("review_status")),
                },
                {
                    "label": "Support state",
                    "current": _status_label(current.get("support_state")),
                    "proposed": _status_label(proposed.get("support_state")),
                },
                {
                    "label": "Activated modeled fields",
                    "current": ", ".join(current_fields) if current_fields else "None",
                    "proposed": ", ".join(proposed_fields) if proposed_fields else "None",
                },
                {
                    "label": "Review flags",
                    "current": ", ".join(current_flags) if current_flags else "None",
                    "proposed": ", ".join(proposed_flags) if proposed_flags else "None",
                },
            ]
            if "character_projection_changed" in proposed:
                rows.append(
                    {
                        "label": "Selected Character projection changes",
                        "current": "Not compared",
                        "proposed": (
                            "Yes"
                            if proposed.get("character_projection_changed") is True
                            else "No"
                        ),
                    }
                )
            return {
                "state": "preview_ready",
                "state_label": "Preview ready",
                "disclosure": preview.disclosure,
                "rows": rows,
            }

        if review.row.entry_type == "monster":
            current = dict(preview.current)
            proposed = dict(preview.proposed)

            def value(payload: Mapping[str, object], key: str) -> str:
                raw = payload.get(key)
                return "Not set" if raw is None or raw == "" else str(raw)

            rows = [
                {
                    "label": label,
                    "current": value(current, key),
                    "proposed": value(proposed, key),
                }
                for key, label in (
                    ("max_hp", "Future-seed HP"),
                    ("movement_total", "Future-seed movement"),
                    ("initiative_bonus", "Initiative modifier"),
                    ("dexterity_modifier", "DEX modifier"),
                    ("resource_note_count", "Resource note count"),
                )
            ]
            current_counters = list(current.get("resource_counters") or ())[:50]
            proposed_counters = list(proposed.get("resource_counters") or ())[:50]
            return {
                "state": "preview_ready",
                "state_label": "Preview ready",
                "disclosure": preview.disclosure,
                "rows": rows,
                "current_counters": [
                    {
                        "position": int(dict(item).get("position") or 0),
                        "value": str(dict(item).get("current_value") or 0),
                        "maximum": str(dict(item).get("max_value") or 0),
                        "reset": _humanize(dict(item).get("reset_kind")) or "None",
                        "threshold": str(
                            dict(item).get("recharge_threshold") or "None"
                        ),
                    }
                    for item in current_counters
                    if isinstance(item, Mapping)
                ],
                "proposed_counters": [
                    {
                        "position": int(dict(item).get("position") or 0),
                        "value": str(dict(item).get("current_value") or 0),
                        "maximum": str(dict(item).get("max_value") or 0),
                        "reset": _humanize(dict(item).get("reset_kind")) or "None",
                        "threshold": str(
                            dict(item).get("recharge_threshold") or "None"
                        ),
                    }
                    for item in proposed_counters
                    if isinstance(item, Mapping)
                ],
            }
        return {
            "state": "preview_not_supported",
            "state_label": "Preview not supported",
            "disclosure": (
                "This entry type remains reference-only for preview; no modeled "
                "activation is implied."
            ),
            "rows": [],
        }


def error_presentation(*, stale: bool = False) -> dict[str, object]:
    return {
        "state": "stale" if stale else "error",
        "message": (
            MECHANICS_IMPACT_BROWSER_STALE_MESSAGE
            if stale
            else MECHANICS_IMPACT_BROWSER_ERROR_MESSAGE
        ),
    }
