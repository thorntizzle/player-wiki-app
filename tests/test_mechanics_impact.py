from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest
from flask import g

from player_wiki.db import get_db
from player_wiki.mechanics_impact import (
    MechanicsImpactAccessContext,
    MechanicsImpactCursorCodec,
    MechanicsImpactCursorError,
    MechanicsImpactDenied,
    MechanicsImpactIdentity,
    MechanicsImpactInvalidMetadata,
    MechanicsImpactKernel,
    MechanicsImpactMetadataRow,
    mechanics_impact_statuses,
    normalize_mechanics_impact_state,
    validate_mechanics_impact_statuses,
)
from player_wiki.source_health import (
    SourceHealthConsumer,
    SourceHealthInventoryPage,
    SourceHealthReference,
)
from player_wiki.systems_models import SystemsEntryRecord
from player_wiki.systems_service import SystemsService
from tests.sample_data import ASSIGNED_CHARACTER_SLUG


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _entry(
    *,
    entry_key: str = "item|TST|blade",
    entry_type: str = "item",
    metadata: dict[str, object] | None = None,
    body: dict[str, object] | None = None,
) -> SystemsEntryRecord:
    return SystemsEntryRecord(
        id=1,
        library_slug="TEST-LIBRARY",
        source_id="TST",
        entry_key=entry_key,
        entry_type=entry_type,
        slug="test-entry",
        title="Private title",
        source_page="",
        source_path="private/source.json",
        search_text="private search text",
        player_safe_default=False,
        dm_heavy=True,
        metadata=dict(metadata or {}),
        body=dict(body or {}),
        rendered_html="<p>private body</p>",
        created_at=NOW,
        updated_at=NOW,
    )


class _QueueStore:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.snapshots = 0
        self.scans = 0

    def mechanics_impact_metadata_snapshot(self, library_slug):
        self.snapshots += 1
        return "snapshot-a"

    def scan_mechanics_impact_metadata(self, library_slug, *, after, limit):
        self.scans += 1
        return self.rows[:limit], False


class _KernelService:
    def __init__(self, entry, *, accessible_identities=None):
        self.entry = entry
        self.accessible_identities = accessible_identities
        self.authorization_calls = []
        self.dispatch_calls = 0

    def mechanics_impact_destination(self, campaign_slug, slug):
        return f"/campaigns/{campaign_slug}/systems/entries/{slug}"

    def mechanics_impact_consumer_destination(
        self, campaign_slug, owner_id, destination
    ):
        return destination

    def resolve_mechanics_impact_entry(self, identity):
        expected = MechanicsImpactIdentity(
            self.entry.library_slug, self.entry.source_id, self.entry.entry_key
        )
        return self.entry if identity == expected else None

    def filter_mechanics_impact_authorized_identities(self, context, identities):
        self.authorization_calls.append((context, tuple(identities)))
        if self.accessible_identities is None:
            return frozenset(identities)
        return frozenset(identities) & frozenset(self.accessible_identities)

    def filter_mechanics_impact_consumers(self, context, entry, consumers):
        return tuple(
            consumer
            for consumer in consumers
            if consumer.reference.entry_key == entry.entry_key
        )

    def mechanics_impact_input_digest(self, entry):
        return SystemsService.mechanics_impact_input_digest(entry)

    def dispatch_mechanics_impact_preview(
        self, current, proposed, *, character_projection=None
    ):
        self.dispatch_calls += 1
        service = object.__new__(SystemsService)
        return SystemsService.dispatch_mechanics_impact_preview(
            service,
            current,
            proposed,
            character_projection=character_projection,
        )


def _context(*, owner_capabilities=()):
    return MechanicsImpactAccessContext(
        campaign_slug="campaign-a",
        system_code="DND-5E",
        library_slug="TEST-LIBRARY",
        can_manage_systems=True,
        owner_capabilities=tuple(owner_capabilities),
    )


def _kernel(
    *,
    entry=None,
    rows=(),
    authorize=lambda _slug: _context(),
    adapters=None,
    character_preview=None,
    character_authorize=None,
    accessible_identities=None,
    clock=lambda: NOW,
):
    selected = entry or _entry(
        metadata={
            "campaign_item_mechanics_review_status": "draft",
            "campaign_item_mechanics_support_state": "needs_implementation",
        }
    )
    service = _KernelService(
        selected,
        accessible_identities=accessible_identities,
    )
    return MechanicsImpactKernel(
        store=_QueueStore(rows),
        systems_service=service,
        authorize=authorize,
        inventory_adapters=adapters or {},
        cursor_codec=MechanicsImpactCursorCodec(b"test-signing-key-32-bytes-long!!"),
        character_preview=character_preview,
        character_authorize=character_authorize,
        clock=clock,
    )


def test_status_normalization_preserves_separate_precedence_and_fails_unknown_closed():
    assert normalize_mechanics_impact_state(" Manual-Review ") == "manual_review"
    assert normalize_mechanics_impact_state("manual review") == "manual review"
    assert mechanics_impact_statuses(
        {
            "campaign_item_mechanics_review_status": "draft",
            "review_status": "approved",
            "campaign_item_mechanics_support_state": "unsupported",
            "support_state": "modeled",
        }
    ) == ("draft", "unsupported")
    with pytest.raises(MechanicsImpactInvalidMetadata, match="Invalid mechanics review"):
        validate_mechanics_impact_statuses({"review_status": "manual review"})
    with pytest.raises(MechanicsImpactInvalidMetadata, match="Invalid mechanics review"):
        validate_mechanics_impact_statuses({"review_status": 0})


def test_app_composes_read_only_kernel_without_registering_a_10b_route(app):
    kernel = app.extensions["mechanics_impact_kernel"]
    assert isinstance(kernel, MechanicsImpactKernel)
    assert not any("mechanics-impact" in rule.rule for rule in app.url_map.iter_rules())


def _set_effective_actor(app, users, actor_name, *, authenticated_name=None):
    auth_store = app.extensions["auth_store"]
    actor = (
        auth_store.get_user_by_id(users[actor_name]["id"])
        if actor_name is not None
        else None
    )
    authenticated = (
        auth_store.get_user_by_id(users[authenticated_name]["id"])
        if authenticated_name is not None
        else actor
    )
    g.current_user = actor
    g.current_memberships = (
        auth_store.list_memberships_for_user(actor.id, statuses=("active",))
        if actor is not None
        else []
    )
    g.authenticated_user = authenticated
    g.authenticated_memberships = (
        auth_store.list_memberships_for_user(authenticated.id, statuses=("active",))
        if authenticated is not None
        else []
    )
    g.view_as_user = actor if authenticated is not actor else None
    g.current_auth_source = "view_as" if authenticated is not actor else "session"


def test_app_admission_uses_effective_actor_and_systems_scope(app, users):
    kernel = app.extensions["mechanics_impact_kernel"]

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, None)
        with pytest.raises(MechanicsImpactDenied):
            kernel.list_queue("linden-pass")

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, "party")
        with pytest.raises(MechanicsImpactDenied):
            kernel.list_queue("linden-pass")

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, "dm")
        assert kernel.list_queue("linden-pass").rows == ()

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, "party", authenticated_name="admin")
        with pytest.raises(MechanicsImpactDenied):
            kernel.list_queue("linden-pass")

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, "dm", authenticated_name="admin")
        assert kernel.list_queue("linden-pass").rows == ()

    with app.app_context():
        app.extensions["auth_store"].upsert_campaign_visibility_setting(
            "linden-pass", "systems", visibility="private"
        )

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, "dm")
        with pytest.raises(MechanicsImpactDenied):
            kernel.list_queue("linden-pass")

    with app.test_request_context("/campaigns/linden-pass/systems"):
        _set_effective_actor(app, users, "admin")
        assert kernel.list_queue("linden-pass").rows == ()


def test_app_queue_visibility_is_batched_cache_free_and_excludes_disabled_rows(
    app, users, monkeypatch
):
    source_rows = (
        ("MI-PUB", "public", True, True, None),
        ("MI-PLAY", "players", True, True, None),
        ("MI-DM", "dm", True, True, None),
        ("MI-PRIVATE", "private", True, True, None),
        ("MI-ENTRY-PRIVATE", "players", True, True, "private"),
        ("MI-OFF-SOURCE", "players", False, True, None),
        ("MI-OFF-ENTRY", "players", True, False, None),
    )
    identities = {}
    with app.app_context():
        store = app.extensions["systems_store"]
        store.upsert_library("DND-5E", title="DND-5E", system_code="DND-5E")
        for (
            source_id,
            visibility,
            source_enabled,
            entry_enabled,
            entry_visibility,
        ) in source_rows:
            store.upsert_source(
                "DND-5E",
                source_id,
                title=source_id,
                license_class="custom_campaign",
                public_visibility_allowed=True,
            )
            entry_key = f"item|{source_id}|review"
            store.upsert_entry(
                "DND-5E",
                source_id,
                entry_key=entry_key,
                entry_type="item",
                slug=source_id.lower(),
                title=f"Private {source_id} title",
                metadata={"review_status": "draft"},
            )
            store.upsert_campaign_enabled_source(
                "linden-pass",
                library_slug="DND-5E",
                source_id=source_id,
                is_enabled=source_enabled,
                default_visibility=visibility,
            )
            if not entry_enabled or entry_visibility is not None:
                store.upsert_campaign_entry_override(
                    "linden-pass",
                    library_slug="DND-5E",
                    entry_key=entry_key,
                    visibility_override=entry_visibility,
                    is_enabled_override=False if not entry_enabled else None,
                )
            identities[source_id] = entry_key

        original_resolver = store.resolve_source_health_targets
        authorization_reads = []

        def counted_resolver(*args, **kwargs):
            authorization_reads.append(tuple(kwargs["references"]))
            return original_resolver(*args, **kwargs)

        monkeypatch.setattr(store, "resolve_source_health_targets", counted_resolver)
        # Isolate the mechanics read boundary from the app's ordinary first
        # repository load, which seeds the sanitized page fixture database.
        app.extensions["repository_store"].get()
        changes_before_reads = get_db().total_changes

        with app.test_request_context("/campaigns/linden-pass/systems"):
            _set_effective_actor(app, users, "dm")
            dm_rows = app.extensions["mechanics_impact_kernel"].list_queue(
                "linden-pass"
            ).rows
            assert not hasattr(g, "_systems_service_request_cache")

        assert len(authorization_reads) == 1
        assert len(authorization_reads[0]) == len(source_rows)
        assert {row.identity.entry_key for row in dm_rows} == {
            identities["MI-PUB"],
            identities["MI-PLAY"],
            identities["MI-DM"],
        }

        authorization_reads.clear()
        with app.test_request_context("/campaigns/linden-pass/systems"):
            _set_effective_actor(app, users, "admin")
            admin_rows = app.extensions["mechanics_impact_kernel"].list_queue(
                "linden-pass"
            ).rows
        assert len(authorization_reads) == 1
        assert {row.identity.entry_key for row in admin_rows} == {
            identities["MI-PUB"],
            identities["MI-PLAY"],
            identities["MI-DM"],
            identities["MI-PRIVATE"],
            identities["MI-ENTRY-PRIVATE"],
        }

        authorization_reads.clear()
        with app.test_request_context("/campaigns/linden-pass/systems"):
            _set_effective_actor(app, users, "dm", authenticated_name="admin")
            view_as_rows = app.extensions["mechanics_impact_kernel"].list_queue(
                "linden-pass"
            ).rows
        assert len(authorization_reads) == 1
        assert {row.identity.entry_key for row in view_as_rows} == {
            identities["MI-PUB"],
            identities["MI-PLAY"],
            identities["MI-DM"],
        }

        kernel = app.extensions["mechanics_impact_kernel"]
        monkeypatch.setitem(
            kernel._inventory_adapters,
            "characters",
            lambda *_args: pytest.fail(
                "target authorization must precede the owner adapter"
            ),
        )
        monkeypatch.setattr(
            app.extensions["systems_service"],
            "dispatch_mechanics_impact_preview",
            lambda *_args, **_kwargs: pytest.fail(
                "target authorization must precede the interpreter"
            ),
        )
        for source_id in (
            "MI-PRIVATE",
            "MI-ENTRY-PRIVATE",
            "MI-OFF-SOURCE",
            "MI-OFF-ENTRY",
        ):
            identity = MechanicsImpactIdentity(
                "DND-5E", source_id, identities[source_id]
            )
            with app.test_request_context("/campaigns/linden-pass/systems"):
                _set_effective_actor(app, users, "dm")
                with pytest.raises(MechanicsImpactDenied, match="unavailable"):
                    kernel.list_affected_consumers(
                        "linden-pass", identity, owner_id="characters"
                    )
                with pytest.raises(MechanicsImpactDenied, match="unavailable"):
                    kernel.preview(
                        "linden-pass",
                        identity,
                        expected_updated_at="",
                        expected_input_digest="",
                        proposed_entry=_entry(),
                    )
        assert get_db().total_changes == changes_before_reads


def test_store_metadata_scan_orders_attention_and_never_loads_entry_bodies(app):
    with app.app_context():
        store = app.extensions["systems_store"]
        store.upsert_library(
            "TEST-LIBRARY", title="Test", system_code="DND-5E"
        )
        store.upsert_source(
            "TEST-LIBRARY",
            "TST",
            title="Test source",
            license_class="custom_campaign",
        )
        states = (
            ("reference", "reference_only"),
            ("draft", "draft"),
            ("manual", "manual-review"),
            ("unsupported", "unsupported"),
            ("needed", "needs-implementation"),
            ("approved", "modeled"),
        )
        for index, (entry_key, support) in enumerate(states):
            store.upsert_entry(
                "TEST-LIBRARY",
                "TST",
                entry_key=entry_key,
                entry_type="item",
                slug=f"entry-{index}",
                title=f"Entry {index}",
                metadata={
                    "review_status": "approved" if entry_key != "draft" else "draft",
                    "support_state": support,
                },
                body={"secret": "must not be selected"},
                rendered_html="<p>must not be selected</p>",
            )
        connection = get_db()
        changes_before_read = connection.total_changes
        rows, has_more = store.scan_mechanics_impact_metadata(
            "TEST-LIBRARY", limit=2
        )
        assert has_more
        assert [row.identity.entry_key for row in rows] == ["needed", "unsupported"]
        first_page_last = rows[-1]
        review, support = mechanics_impact_statuses(first_page_last.metadata)
        from player_wiki.mechanics_impact import mechanics_impact_attention_rank

        remaining, remaining_has_more = store.scan_mechanics_impact_metadata(
            "TEST-LIBRARY",
            after=(
                mechanics_impact_attention_rank(review, support),
                first_page_last.identity.source_id,
                first_page_last.identity.entry_key,
                first_page_last.row_id,
            ),
            limit=50,
        )
        assert not remaining_has_more
        assert [row.identity.entry_key for row in rows + remaining] == [
            "needed",
            "unsupported",
            "manual",
            "draft",
            "reference",
        ]
        assert all(not hasattr(row, "body") for row in rows + remaining)
        assert len(rows + remaining) <= 200
        assert connection.total_changes == changes_before_read


def test_queue_is_bounded_private_and_performs_zero_consumer_reads():
    raw = MechanicsImpactMetadataRow(
        row_id=7,
        identity=MechanicsImpactIdentity("TEST-LIBRARY", "TST", "item|TST|blade"),
        entry_type="item",
        slug="test-entry",
        metadata={
            "review_status": "draft",
            "support_state": "needs_implementation",
            "private": "not serialized",
        },
        updated_at=NOW,
    )
    consumer_calls = []
    kernel = _kernel(
        rows=(raw,),
        adapters={
            "characters": lambda *_args: consumer_calls.append(True),
        },
    )
    page = kernel.list_queue("campaign-a")
    payload = page.to_payload()
    assert page.inspected_rows == 1
    assert consumer_calls == []
    assert payload["payload_policy"]["cache_control"] == "private, no-store"
    assert "not serialized" not in json.dumps(payload)
    assert len(json.dumps(payload).encode("utf-8")) <= 65_536


def test_queue_and_selected_rows_require_batched_target_authorization_before_use():
    allowed_identity = MechanicsImpactIdentity(
        "TEST-LIBRARY", "TST", "item|TST|allowed"
    )
    denied_identity = MechanicsImpactIdentity(
        "TEST-LIBRARY", "PRIVATE", "item|PRIVATE|hidden"
    )
    rows = tuple(
        MechanicsImpactMetadataRow(
            row_id=index,
            identity=identity,
            entry_type="item",
            slug=f"row-{index}",
            metadata={"review_status": "draft"},
            updated_at=NOW,
        )
        for index, identity in enumerate((allowed_identity, denied_identity), start=1)
    )
    selected = _entry(
        entry_key=denied_identity.entry_key,
        metadata={"review_status": "draft"},
    )
    selected = replace(selected, source_id=denied_identity.source_id)
    adapter_calls = []
    kernel = _kernel(
        entry=selected,
        rows=rows,
        accessible_identities=(allowed_identity,),
        authorize=lambda _slug: _context(
            owner_capabilities=(("characters", True),)
        ),
        adapters={
            "characters": lambda *_args: adapter_calls.append(True)
        },
    )

    page = kernel.list_queue("campaign-a")
    assert [row.identity for row in page.rows] == [allowed_identity]
    assert len(kernel.systems_service.authorization_calls) == 1
    assert kernel.systems_service.authorization_calls[0][1] == (
        allowed_identity,
        denied_identity,
    )

    with pytest.raises(MechanicsImpactDenied, match="unavailable"):
        kernel.list_affected_consumers(
            "campaign-a", denied_identity, owner_id="characters"
        )
    assert adapter_calls == []

    with pytest.raises(MechanicsImpactDenied, match="unavailable"):
        kernel.preview(
            "campaign-a",
            denied_identity,
            expected_updated_at=selected.updated_at.isoformat(),
            expected_input_digest=SystemsService.mechanics_impact_input_digest(selected),
            proposed_entry=selected,
        )
    assert kernel.systems_service.dispatch_calls == 0


def test_effective_actor_admission_precedes_queue_store_and_owner_reads():
    kernel = _kernel(authorize=lambda _slug: None)
    with pytest.raises(MechanicsImpactDenied):
        kernel.list_queue("campaign-a")
    assert kernel.store.snapshots == 0
    assert kernel.store.scans == 0


def test_cursor_is_signed_campaign_bound_and_time_bounded():
    codec = MechanicsImpactCursorCodec(b"test-signing-key-32-bytes-long!!")
    token = codec.encode(
        {
            "kind": "queue",
            "campaign": "campaign-a",
            "library": "TEST-LIBRARY",
            "iat": int(NOW.timestamp()),
            "snapshot": "snapshot-a",
            "after": [0, "TST", "entry", 1],
        }
    )
    with pytest.raises(MechanicsImpactCursorError):
        codec.decode(token[:-1] + ("A" if token[-1] != "A" else "B"))
    stale_kernel = _kernel(clock=lambda: NOW + timedelta(minutes=16))
    with pytest.raises(MechanicsImpactCursorError, match="Stale"):
        stale_kernel.list_queue("campaign-a", continuation=token)
    with pytest.raises(MechanicsImpactDenied):
        _kernel().list_queue("campaign-b", continuation=token)


@pytest.mark.parametrize("owner_id", ("characters", "mechanics", "combat", "presets"))
def test_consumer_owner_capability_is_checked_before_adapter_and_exact_ref_filtering(
    owner_id,
):
    entry = _entry()
    identity = MechanicsImpactIdentity(
        entry.library_slug, entry.source_id, entry.entry_key
    )
    calls = []

    def adapter(_context, _continuation):
        calls.append(True)
        return SourceHealthInventoryPage(
            consumers=(
                SourceHealthConsumer(
                    consumer_type="character",
                    consumer_key="hero:equipment_catalog[0].systems_ref",
                    surface="Character",
                    reference=SourceHealthReference(
                        target_kind="systems", entry_key=entry.entry_key
                    ),
                    destination="/campaigns/campaign-a/characters/hero",
                ),
                SourceHealthConsumer(
                    consumer_type="character",
                    consumer_key="hero:equipment_catalog[1].systems_ref",
                    surface="Character",
                    reference=SourceHealthReference(
                        target_kind="systems", entry_key="other"
                    ),
                    destination="/campaigns/campaign-a/characters/hero",
                ),
            ),
            definition_file_count=1,
            definition_bytes=100,
        )

    denied = _kernel(entry=entry, adapters={owner_id: adapter})
    assert denied.list_affected_consumers(
        "campaign-a", identity, owner_id=owner_id
    ).rows == ()
    assert calls == []

    allowed = _kernel(
        entry=entry,
        adapters={owner_id: adapter},
        authorize=lambda _slug: _context(
            owner_capabilities=((owner_id, True),)
        ),
    )
    result = allowed.list_affected_consumers(
        "campaign-a", identity, owner_id=owner_id
    )
    assert len(result.rows) == 1
    assert result.rows[0].consumer_key.endswith("equipment_catalog[0].systems_ref")
    assert result.definition_file_count == 1
    assert "Private title" not in json.dumps(result.to_payload())


def test_item_preview_refuses_drift_and_derives_at_most_one_authorized_character():
    current = _entry(
        metadata={
            "campaign_item_mechanics_review_status": "draft",
            "campaign_item_mechanics_support_state": "needs_implementation",
            "bonus_ac": 1,
        }
    )
    proposed = replace(
        current,
        metadata={
            **current.metadata,
            "campaign_item_mechanics_review_status": "approved",
            "campaign_item_mechanics_support_state": "modeled",
            "bonus_ac": 2,
        },
    )
    identity = MechanicsImpactIdentity(
        current.library_slug, current.source_id, current.entry_key
    )
    calls = []
    kernel = _kernel(
        entry=current,
        authorize=lambda _slug: _context(
            owner_capabilities=(("characters", True),)
        ),
        character_preview=lambda campaign, character, old, new: (
            calls.append((campaign, character, old.entry_key, new.entry_key))
            or ("old-digest", "new-digest")
        ),
        character_authorize=lambda campaign, character: character == "hero",
    )
    digest = SystemsService.mechanics_impact_input_digest(current)
    assert digest != SystemsService.mechanics_impact_input_digest(
        replace(current, metadata={**current.metadata, "bonus_ac": 9})
    )
    stale = kernel.preview(
        "campaign-a",
        identity,
        expected_updated_at=current.updated_at.isoformat(),
        expected_input_digest="0" * 64,
        proposed_entry=proposed,
    )
    assert stale.state == "stale_review"
    assert calls == []
    preview = kernel.preview(
        "campaign-a",
        identity,
        expected_updated_at=current.updated_at.isoformat(),
        expected_input_digest=digest,
        proposed_entry=proposed,
        character_slug="hero",
    )
    assert preview.state == "preview_ready"
    assert calls == [("campaign-a", "hero", current.entry_key, current.entry_key)]
    assert preview.current["activated_modeled_fields"] == ()
    assert preview.proposed["activated_modeled_fields"] == ("bonus_ac",)
    assert preview.proposed["character_projection_changed"] is True
    with pytest.raises(MechanicsImpactDenied):
        kernel.preview(
            "campaign-a",
            identity,
            expected_updated_at=current.updated_at.isoformat(),
            expected_input_digest=digest,
            proposed_entry=proposed,
            character_slug="other",
        )


def test_app_character_preview_requires_exact_entry_key_and_source_id(
    app, monkeypatch
):
    current = replace(
        _entry(
            entry_key="item|EXPECTED|collision",
            metadata={"review_status": "draft"},
        ),
        library_slug="DND-5E",
        source_id="EXPECTED",
    )
    proposed = replace(
        current,
        metadata={"review_status": "approved", "support_state": "modeled"},
    )
    kernel = app.extensions["mechanics_impact_kernel"]
    character_repository = app.extensions["character_repository"]

    with app.app_context():
        app.extensions["systems_store"].upsert_library(
            "DND-5E", title="DND-5E", system_code="DND-5E"
        )
        record = character_repository.get_character(
            "linden-pass", ASSIGNED_CHARACTER_SLUG
        )
        assert record is not None
        monkeypatch.setattr(
            character_repository,
            "get_combat_seed_character",
            lambda *_args, **_kwargs: record,
        )

        projection_calls = []

        def fake_projection(**kwargs):
            projection_calls.append(kwargs["systems_service"])
            return {
                "definition": record.definition,
                "state": {},
                "visible_attacks": [],
                "attack_reminders": [],
                "defensive_rules": [],
                "item_use_actions": [],
            }

        monkeypatch.setattr("player_wiki.app.build_character_mechanics_projection", fake_projection)

        record.definition.equipment_catalog = [
            {
                "name": "Untrusted display title",
                "systems_ref": {
                    "library_slug": "DND-5E",
                    "source_id": "EXPECTED",
                    "entry_key": current.entry_key,
                    "slug": "unrelated-slug",
                },
            }
        ]
        kernel._character_preview(
            "linden-pass", ASSIGNED_CHARACTER_SLUG, current, proposed
        )
        assert len(projection_calls) == 2

        for systems_ref in (
            {
                "library_slug": "DND-5E",
                "source_id": "WRONG",
                "entry_key": current.entry_key,
            },
            {"slug": current.slug},
            {"title": current.title},
        ):
            record.definition.equipment_catalog = [
                {"name": current.title, "systems_ref": systems_ref}
            ]
            with pytest.raises(ValueError, match="exact Systems item ref"):
                kernel._character_preview(
                    "linden-pass", ASSIGNED_CHARACTER_SLUG, current, proposed
                )
        assert len(projection_calls) == 2


def test_selected_unknown_state_returns_sanitized_invalid_metadata_result():
    invalid = _entry(metadata={"review_status": "unexpected private value"})
    identity = MechanicsImpactIdentity(
        invalid.library_slug, invalid.source_id, invalid.entry_key
    )
    kernel = _kernel(
        entry=invalid,
        authorize=lambda _slug: _context(
            owner_capabilities=(("characters", True),)
        ),
        adapters={
            "characters": lambda *_args: pytest.fail("owner adapter must not run")
        },
    )
    consumers = kernel.list_affected_consumers(
        "campaign-a", identity, owner_id="characters"
    )
    assert consumers.state == "invalid_metadata"
    assert consumers.rows == ()
    assert "unexpected private value" not in json.dumps(consumers.to_payload())
    preview = kernel.preview(
        "campaign-a",
        identity,
        expected_updated_at=invalid.updated_at.isoformat(),
        expected_input_digest="",
        proposed_entry=invalid,
    )
    assert preview.state == "invalid_metadata"
    assert "unexpected private value" not in json.dumps(preview.to_payload())


def test_monster_and_unsupported_preview_reuse_only_existing_dispatchers():
    service = object.__new__(SystemsService)
    monster = _entry(
        entry_key="monster|TST|wolf",
        entry_type="monster",
        metadata={
            "review_status": "manual_review",
            "support_state": "unsupported",
            "hp": {"average": 11},
            "speed": {"walk": 40},
            "abilities": {"dex": 15},
        },
        body={"action": "Howl (Recharge 5-6)"},
    )
    proposed = replace(monster, metadata={**monster.metadata, "hp": {"average": 20}})
    payload = SystemsService.dispatch_mechanics_impact_preview(
        service, monster, proposed
    )
    assert payload["state"] == "preview_ready"
    assert payload["current"]["max_hp"] == 11
    assert payload["proposed"]["max_hp"] == 20
    assert "existing presets and active combatants remain unchanged" in payload[
        "disclosure"
    ]
    unsupported = replace(monster, entry_type="spell")
    unsupported_payload = SystemsService.dispatch_mechanics_impact_preview(
        service, unsupported, unsupported
    )
    assert unsupported_payload["state"] == "preview_not_supported"
    assert unsupported_payload["current"] == {}
