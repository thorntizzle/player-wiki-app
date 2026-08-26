from __future__ import annotations

from dataclasses import replace

import pytest

from player_wiki.auth_store import AuthStore
from player_wiki.campaign_combat_preset_service import (
    CampaignCombatPresetAuthorizationContext,
    CampaignCombatPresetAuthorizationError,
    CampaignCombatPresetService,
    CampaignCombatPresetValidationError,
)
from player_wiki.campaign_combat_preset_store import (
    CampaignCombatPresetConflictError,
    CampaignCombatPresetStore,
    CampaignCombatPresetStoreHooks,
)
from player_wiki.combat_preset_models import CampaignCombatPresetEntryInput
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics


def _entry(name: str = "Guard") -> CampaignCombatPresetEntryInput:
    return CampaignCombatPresetEntryInput(
        source_kind="manual_npc",
        custom_name=name,
        initiative_bonus=1,
        dexterity_modifier=2,
        max_hp=12,
        movement_total=30,
    )


def _context(
    actor_user_id: int,
    *,
    campaign_slug: str = "linden-pass",
    can_manage_combat: bool = True,
    is_view_as: bool = False,
    is_read_only: bool = False,
) -> CampaignCombatPresetAuthorizationContext:
    return CampaignCombatPresetAuthorizationContext(
        campaign_slug=campaign_slug,
        actor_user_id=actor_user_id,
        can_manage_combat=can_manage_combat,
        is_view_as=is_view_as,
        is_read_only=is_read_only,
    )


def _service(app, **context_overrides) -> CampaignCombatPresetService:
    actor_user_id = app.config["TEST_USERS"]["dm"]["id"]
    context = _context(actor_user_id, **context_overrides)
    return CampaignCombatPresetService(
        CampaignCombatPresetStore(),
        AuthStore(),
        authorization_adapter=lambda _campaign_slug: context,
    )


def _preset_events() -> list:
    return [
        event
        for event in AuthStore().list_recent_audit_events(limit=100)
        if event.event_type.startswith("campaign_encounter_preset_")
    ]


@pytest.mark.parametrize("is_admin", [False, True])
def test_direct_manager_context_supports_full_crud_and_exact_audit_order(app, is_admin):
    with app.app_context():
        actor_key = "admin" if is_admin else "dm"
        actor_user_id = app.config["TEST_USERS"][actor_key]["id"]
        service = CampaignCombatPresetService(
            CampaignCombatPresetStore(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(actor_user_id),
        )

        created = service.create_preset(
            "linden-pass",
            name="  Ｇuard Post  ",
            entries=(_entry("First"), _entry("Second")),
        )
        listed = service.list_presets("linden-pass")
        loaded = service.get_preset("linden-pass", created.id)
        updated = service.update_preset(
            "linden-pass",
            str(created.id),
            expected_revision=str(created.revision),
            name="Guard Post Revised",
            entries=(created.entries[1], created.entries[0]),
        )
        service.delete_preset(
            "linden-pass",
            created.id,
            expected_revision=updated.revision,
        )

        assert created.name == "Guard Post"
        assert listed == [created.without_entries()]
        assert loaded == created
        assert [entry.id for entry in updated.entries] == [
            created.entries[1].id,
            created.entries[0].id,
        ]
        assert service.get_preset("linden-pass", created.id) is None

        events = list(reversed(_preset_events()))
        assert [event.event_type for event in events] == [
            "campaign_encounter_preset_created",
            "campaign_encounter_preset_updated",
            "campaign_encounter_preset_deleted",
        ]
        assert all(event.actor_user_id == actor_user_id for event in events)
        assert [event.metadata for event in events] == [
            {"entry_count": 2, "preset_id": created.id, "revision": 1},
            {
                "entry_count": 2,
                "preset_id": created.id,
                "previous_revision": 1,
                "revision": 2,
            },
            {"entry_count": 2, "preset_id": created.id, "revision": 2},
        ]


def test_view_as_dm_reads_use_effective_manager_but_real_actor_owns_audit_identity(app):
    with app.app_context():
        real_actor_id = app.config["TEST_USERS"]["admin"]["id"]
        direct = _service(app)
        created = direct.create_preset("linden-pass", name="Readable", entries=())
        viewed = CampaignCombatPresetService(
            CampaignCombatPresetStore(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(
                real_actor_id,
                can_manage_combat=True,
                is_view_as=True,
                is_read_only=True,
            ),
        )

        assert viewed.list_presets("linden-pass") == [created.without_entries()]
        assert viewed.get_preset("linden-pass", created.id) == created
        assert _preset_events()[0].actor_user_id == app.config["TEST_USERS"]["dm"]["id"]


class _ExplodingPayload:
    def __int__(self):
        raise AssertionError("payload parsed before authorization")

    def __iter__(self):
        raise AssertionError("entries parsed before authorization")


class _NoStoreAccess:
    def __getattr__(self, _name):
        raise AssertionError("store accessed before authorization")


@pytest.mark.parametrize(
    "context",
    [
        _context(1, can_manage_combat=False),
        _context(1, campaign_slug="other-campaign"),
        _context(1, is_view_as=True, is_read_only=True),
    ],
)
def test_denied_mutations_precede_all_payload_parsing_and_store_access(app, context):
    with app.app_context():
        service = CampaignCombatPresetService(
            _NoStoreAccess(),
            AuthStore(),
            authorization_adapter=lambda _slug: context,
        )
        with pytest.raises(CampaignCombatPresetAuthorizationError):
            service.update_preset(
                "linden-pass",
                _ExplodingPayload(),
                expected_revision=_ExplodingPayload(),
                name=_ExplodingPayload(),
                entries=_ExplodingPayload(),
            )
        assert _preset_events() == []


def test_non_manager_effective_identity_and_mismatched_campaign_deny_reads(app):
    with app.app_context():
        for context in (
            _context(app.config["TEST_USERS"]["admin"]["id"], can_manage_combat=False),
            _context(app.config["TEST_USERS"]["admin"]["id"], campaign_slug="other-campaign"),
        ):
            service = CampaignCombatPresetService(
                _NoStoreAccess(),
                AuthStore(),
                authorization_adapter=lambda _slug, context=context: context,
            )
            with pytest.raises(CampaignCombatPresetAuthorizationError):
                service.get_preset("linden-pass", _ExplodingPayload())


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("list_presets", {"limit": 0}),
        ("list_presets", {"limit": 51}),
        ("list_presets", {"offset": -1}),
        ("get_preset", {"preset_id": 0}),
        ("create_preset", {"name": "", "entries": ()}),
        ("create_preset", {"name": "x" * 321, "entries": ()}),
        ("create_preset", {"name": "Too Many", "entries": tuple(_entry() for _ in range(51))}),
        (
            "update_preset",
            {"preset_id": 1, "expected_revision": 0, "name": "Invalid", "entries": ()},
        ),
        ("delete_preset", {"preset_id": 1, "expected_revision": 0}),
    ],
)
def test_invalid_bounds_fail_before_transactions_or_audit(app, method, kwargs):
    with app.app_context():
        service = _service(app)
        reset_db_query_metrics()
        with pytest.raises(CampaignCombatPresetValidationError):
            getattr(service, method)("linden-pass", **kwargs)
        metrics = get_db_query_metrics()
        assert metrics["commit_count"] == 0
        assert metrics["rollback_count"] == 0
        assert _preset_events() == []


def test_success_commits_once_and_audit_failure_rolls_back_all_preset_bytes(app):
    class FailingAuditStore(AuthStore):
        def insert_audit_event(self, **kwargs):
            super().insert_audit_event(**kwargs)
            raise RuntimeError("injected audit failure")

    with app.app_context():
        service = _service(app)
        reset_db_query_metrics()
        created = service.create_preset("linden-pass", name="Atomic", entries=(_entry(),))
        metrics = get_db_query_metrics()
        assert metrics["commit_count"] == 1
        assert metrics["rollback_count"] == 0

        failing = CampaignCombatPresetService(
            CampaignCombatPresetStore(),
            FailingAuditStore(),
            authorization_adapter=lambda _slug: _context(
                app.config["TEST_USERS"]["dm"]["id"]
            ),
        )
        reset_db_query_metrics()
        with pytest.raises(RuntimeError, match="audit failure"):
            failing.update_preset(
                "linden-pass",
                created.id,
                expected_revision=created.revision,
                name="Must Roll Back",
                entries=created.entries,
            )
        metrics = get_db_query_metrics()
        assert metrics["commit_count"] == 0
        assert metrics["rollback_count"] == 1
        assert CampaignCombatPresetStore().get_preset("linden-pass", created.id) == created
        assert [event.event_type for event in _preset_events()] == [
            "campaign_encounter_preset_created"
        ]


def test_source_semantics_are_deferred_to_the_accepted_store_boundary(app):
    class SemanticBoundaryStore:
        def create_preset(self, _campaign_slug, *, entries, **_kwargs):
            assert get_db().in_transaction is True
            assert entries[0].source_kind == "future-source-kind"
            raise RuntimeError("store owns source semantics")

    with app.app_context():
        service = CampaignCombatPresetService(
            SemanticBoundaryStore(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(
                app.config["TEST_USERS"]["dm"]["id"]
            ),
        )
        with pytest.raises(RuntimeError, match="store owns source semantics"):
            service.create_preset(
                "linden-pass",
                name="Structural Only",
                entries=(CampaignCombatPresetEntryInput(source_kind="future-source-kind"),),
            )
        assert _preset_events() == []


def test_delete_detail_is_captured_inside_the_atomic_write_transaction(app):
    class TransactionCheckingStore(CampaignCombatPresetStore):
        def get_preset(self, campaign_slug, preset_id):
            assert get_db().in_transaction is True
            return super().get_preset(campaign_slug, preset_id)

    with app.app_context():
        created = _service(app).create_preset(
            "linden-pass", name="Delete Snapshot", entries=(_entry(),)
        )
        service = CampaignCombatPresetService(
            TransactionCheckingStore(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(
                app.config["TEST_USERS"]["dm"]["id"]
            ),
        )

        service.delete_preset(
            "linden-pass",
            created.id,
            expected_revision=created.revision,
        )
        assert _preset_events()[0].metadata == {
            "entry_count": 1,
            "preset_id": created.id,
            "revision": created.revision,
        }


def test_store_failure_rolls_back_and_conflicts_never_audit(app):
    def fail_entry(_operation: str, _position: int) -> None:
        raise RuntimeError("injected store failure")

    with app.app_context():
        actor_id = app.config["TEST_USERS"]["dm"]["id"]
        service = CampaignCombatPresetService(
            CampaignCombatPresetStore(
                hooks=CampaignCombatPresetStoreHooks(before_entry_write=fail_entry)
            ),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(actor_id),
        )
        reset_db_query_metrics()
        with pytest.raises(RuntimeError, match="store failure"):
            service.create_preset("linden-pass", name="Broken", entries=(_entry(),))
        assert get_db_query_metrics()["rollback_count"] == 1
        assert CampaignCombatPresetStore().list_presets("linden-pass") == []
        assert _preset_events() == []

        healthy = CampaignCombatPresetService(
            CampaignCombatPresetStore(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(actor_id),
        )
        created = healthy.create_preset("linden-pass", name="Unique", entries=())
        for action in (
            lambda: healthy.create_preset("linden-pass", name=" UNIQUE ", entries=()),
            lambda: healthy.update_preset(
                "linden-pass",
                created.id,
                expected_revision=99,
                name="Stale",
                entries=(),
            ),
            lambda: healthy.delete_preset(
                "other-campaign",
                created.id,
                expected_revision=created.revision,
            ),
        ):
            before_events = _preset_events()
            with pytest.raises((CampaignCombatPresetConflictError, CampaignCombatPresetAuthorizationError)):
                action()
            assert _preset_events() == before_events


def test_missing_and_foreign_aggregate_conflicts_are_campaign_confined_and_unaudited(app):
    with app.app_context():
        service = _service(app)
        foreign = CampaignCombatPresetStore().create_preset(
            "other-campaign",
            name="Foreign",
            entries=(_entry(),),
        )

        for action in (
            lambda: service.update_preset(
                "linden-pass",
                foreign.id,
                expected_revision=foreign.revision,
                name="Cannot Adopt",
                entries=foreign.entries,
            ),
            lambda: service.delete_preset(
                "linden-pass",
                foreign.id,
                expected_revision=foreign.revision,
            ),
            lambda: service.delete_preset(
                "linden-pass",
                999_999,
                expected_revision=1,
            ),
        ):
            with pytest.raises(CampaignCombatPresetConflictError):
                action()

        assert CampaignCombatPresetStore().get_preset("other-campaign", foreign.id) == foreign
        assert _preset_events() == []


def test_crud_preserves_tracker_bytes_and_query_write_ceilings(app):
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO campaign_combat_trackers "
            "(campaign_slug, round_number, revision, updated_at) VALUES (?, ?, ?, ?)",
            ("linden-pass", 7, 11, "unchanged"),
        )
        connection.commit()
        tracker_before = tuple(
            connection.execute(
                "SELECT * FROM campaign_combat_trackers WHERE campaign_slug = ?",
                ("linden-pass",),
            ).fetchone()
        )
        service = _service(app)

        reset_db_query_metrics()
        created = service.create_preset("linden-pass", name="Ceilings", entries=(_entry(),))
        create_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        assert service.list_presets("linden-pass", limit=1, offset=0) == [
            created.without_entries()
        ]
        list_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        assert service.get_preset("linden-pass", created.id) == created
        get_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        updated = service.update_preset(
            "linden-pass",
            created.id,
            expected_revision=created.revision,
            name="Ceilings Updated",
            entries=created.entries,
        )
        update_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        service.delete_preset(
            "linden-pass",
            updated.id,
            expected_revision=updated.revision,
        )
        delete_metrics = get_db_query_metrics()

        assert create_metrics["commit_count"] == 1
        assert create_metrics["write_count"] == 3
        assert list_metrics["query_count"] == 1 and list_metrics["write_count"] == 0
        assert get_metrics["query_count"] == 2 and get_metrics["write_count"] == 0
        assert update_metrics["query_count"] <= 10
        assert update_metrics["write_count"] <= 5
        assert update_metrics["commit_count"] == 1
        assert delete_metrics["query_count"] <= 6
        assert delete_metrics["write_count"] == 2
        assert delete_metrics["commit_count"] == 1
        tracker_after = tuple(
            connection.execute(
                "SELECT * FROM campaign_combat_trackers WHERE campaign_slug = ?",
                ("linden-pass",),
            ).fetchone()
        )
        assert tracker_after == tracker_before


def test_service_is_composed_without_sqlite_reads(app):
    service = app.extensions["campaign_combat_preset_service"]
    assert isinstance(service, CampaignCombatPresetService)


def test_service_construction_does_not_access_sqlite(monkeypatch):
    import player_wiki.campaign_combat_preset_service as service_module

    def fail_db_access():
        raise AssertionError("service construction queried SQLite")

    monkeypatch.setattr(service_module, "get_db", fail_db_access)
    service = CampaignCombatPresetService(
        CampaignCombatPresetStore(),
        AuthStore(),
        authorization_adapter=lambda _slug: _context(1),
    )
    assert isinstance(service, CampaignCombatPresetService)
