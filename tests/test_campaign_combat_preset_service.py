from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from player_wiki.auth_store import AuthStore
from player_wiki.campaign_combat_preset_service import (
    CampaignCombatPresetApplyConflictError,
    CampaignCombatPresetApplyOutcomeUnconfirmedError,
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
from player_wiki.combat_preset_models import CampaignCombatPresetMaterializedSeed
from player_wiki.combat_npc_resources import NpcResourceCounterSeed, NpcResourceNoteSeed
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
    combat_supported: bool = True,
    can_access_systems: bool = True,
    can_access_dm_content: bool = True,
    is_view_as: bool = False,
    is_read_only: bool = False,
) -> CampaignCombatPresetAuthorizationContext:
    return CampaignCombatPresetAuthorizationContext(
        campaign_slug=campaign_slug,
        actor_user_id=actor_user_id,
        can_manage_combat=can_manage_combat,
        combat_supported=combat_supported,
        can_access_systems=can_access_systems,
        can_access_dm_content=can_access_dm_content,
        is_view_as=is_view_as,
        is_read_only=is_read_only,
    )


def _service(app, **context_overrides) -> CampaignCombatPresetService:
    actor_user_id = app.config["TEST_USERS"]["dm"]["id"]
    context = _context(actor_user_id, **context_overrides)
    return CampaignCombatPresetService(
        CampaignCombatPresetStore(),
        AuthStore(),
        combat_store=app.extensions["campaign_combat_store"],
        authorization_adapter=lambda _campaign_slug: context,
        source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
    )


def test_apply_review_and_confirmation_create_one_atomic_additive_receipt(app):
    with app.app_context():
        service = _service(app)
        preset = service.create_preset(
            "linden-pass",
            name="Atomic Patrol",
            entries=(replace(_entry("Patrol Guard"), quantity=2),),
        )

        review = service.review_preset_apply("linden-pass", preset.id)
        assert review.preset == preset
        assert review.tracker_present is False
        assert review.tracker_revision == 0
        assert len(review.operations) == 2

        receipt = service.apply_preset(
            "linden-pass",
            preset.id,
            confirmation_digest=review.confirmation_digest,
        )

        assert receipt.preset_id == preset.id
        assert receipt.preset_revision == preset.revision
        assert receipt.created_combatant_count == 2
        assert receipt.created_counter_count == 0
        assert receipt.created_note_count == 0
        assert receipt.tracker_revision == 2
        connection = get_db()
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_combatants WHERE campaign_slug = ?",
            ("linden-pass",),
        ).fetchone()[0] == 2
        event = _preset_events()[0]
        assert event.event_type == "campaign_encounter_preset_applied"
        assert event.metadata == {
            "preset_id": preset.id,
            "preset_revision": preset.revision,
            "combatant_count": 2,
            "counter_count": 0,
            "note_count": 0,
            "tracker_revision": 2,
        }


def test_apply_digest_fails_closed_when_tracker_baseline_changes(app):
    with app.app_context():
        service = _service(app)
        preset = service.create_preset(
            "linden-pass",
            name="Guarded Patrol",
            entries=(_entry("Guarded"),),
        )
        review = service.review_preset_apply("linden-pass", preset.id)
        app.extensions["campaign_combat_service"].add_npc_combatant(
            "linden-pass",
            display_name="Existing",
            turn_value=1,
            current_hp=1,
            max_hp=1,
            created_by_user_id=app.config["TEST_USERS"]["dm"]["id"],
        )

        with pytest.raises(CampaignCombatPresetApplyConflictError):
            service.apply_preset(
                "linden-pass",
                preset.id,
                confirmation_digest=review.confirmation_digest,
            )

        assert len(app.extensions["campaign_combat_store"].list_combatants("linden-pass")) == 1
        assert [event.event_type for event in _preset_events()] == [
            "campaign_encounter_preset_created"
        ]


def test_apply_all_four_source_kinds_preserves_tracker_and_materializes_resources(app):
    with app.app_context():
        actor_user_id = app.config["TEST_USERS"]["dm"]["id"]
        combat_service = app.extensions["campaign_combat_service"]
        combat_store = app.extensions["campaign_combat_store"]
        existing = combat_service.add_npc_combatant(
            "linden-pass",
            display_name="Existing Sentinel",
            turn_value=99,
            current_hp=40,
            max_hp=40,
            created_by_user_id=actor_user_id,
        )
        combat_store.update_tracker(
            "linden-pass",
            round_number=7,
            current_combatant_id=existing.id,
            updated_by_user_id=actor_user_id,
        )
        tracker_before = combat_store.get_tracker("linden-pass")
        existing_before = combat_store.get_combatant("linden-pass", existing.id)
        assert tracker_before is not None and existing_before is not None

        preset = CampaignCombatPresetStore().create_preset(
            "linden-pass",
            name="Four Sources",
            entries=(
                CampaignCombatPresetEntryInput(source_kind="character", source_ref="arden-march"),
                CampaignCombatPresetEntryInput(source_kind="dm_statblock", source_ref="7"),
                CampaignCombatPresetEntryInput(source_kind="systems_monster", source_ref="monster|MM|owlbear"),
                _entry("Manual Reserve"),
            ),
            created_by_user_id=actor_user_id,
        )
        counter = NpcResourceCounterSeed(
            resource_key="ink-burst",
            label="Ink Burst",
            current_value=3,
            max_value=3,
            reset_label="Day",
            source_label="DM Content",
        )
        note = NpcResourceNoteSeed(
            label="Keen Sight",
            note="Advantage on sight checks.",
            source_label="Systems MM",
        )
        operations = (
            CampaignCombatPresetMaterializedSeed(
                entry_id=preset.entries[0].id, position=0, quantity_index=0,
                source_kind="character", source_ref="arden-march",
                source_version="1" * 64, version_scheme="combat-seed-v1-sha256",
                display_name="Arden March", turn_value=4, initiative_bonus=4,
                dexterity_modifier=2, initiative_priority=1, current_hp=17,
                max_hp=31, temp_hp=5, movement_total=30,
            ),
            CampaignCombatPresetMaterializedSeed(
                entry_id=preset.entries[1].id, position=1, quantity_index=0,
                source_kind="dm_statblock", source_ref="7",
                source_version="2" * 64, version_scheme="combat-seed-v1-sha256",
                display_name="Mute Scribe", turn_value=3, initiative_bonus=1,
                dexterity_modifier=3, initiative_priority=1, current_hp=22,
                max_hp=22, temp_hp=0, movement_total=30,
                resource_counter_seeds=(counter,),
            ),
            CampaignCombatPresetMaterializedSeed(
                entry_id=preset.entries[2].id, position=2, quantity_index=0,
                source_kind="systems_monster", source_ref="monster|MM|owlbear",
                source_version="3" * 64, version_scheme="combat-seed-v1-sha256",
                display_name="Owlbear", turn_value=1, initiative_bonus=1,
                dexterity_modifier=1, initiative_priority=1, current_hp=59,
                max_hp=59, temp_hp=0, movement_total=40,
                resource_note_seeds=(note,),
            ),
            CampaignCombatPresetMaterializedSeed(
                entry_id=preset.entries[3].id, position=3, quantity_index=0,
                source_kind="manual_npc", source_ref="", source_version=None,
                version_scheme=None, display_name="Manual Reserve", turn_value=1,
                initiative_bonus=1, dexterity_modifier=2, initiative_priority=1,
                current_hp=12, max_hp=12, temp_hp=0, movement_total=30,
            ),
        )

        class StaticResolver:
            @staticmethod
            def resolve_entries_for_apply(_campaign_slug, _entries):
                return operations

        service = CampaignCombatPresetService(
            CampaignCombatPresetStore(),
            AuthStore(),
            combat_store=combat_store,
            authorization_adapter=lambda _slug: _context(actor_user_id),
            source_resolver=StaticResolver(),
        )
        review = service.review_preset_apply("linden-pass", preset.id)
        reset_db_query_metrics()
        receipt = service.apply_preset(
            "linden-pass", preset.id, confirmation_digest=review.confirmation_digest
        )
        metrics = get_db_query_metrics()

        tracker_after = combat_store.get_tracker("linden-pass")
        assert tracker_after is not None
        assert tracker_after.revision == tracker_before.revision + 1
        assert tracker_after.round_number == 7
        assert tracker_after.current_combatant_id == existing.id
        assert combat_store.get_combatant("linden-pass", existing.id) == existing_before
        assert receipt.created_combatant_count == 4
        assert receipt.created_counter_count == 1
        assert receipt.created_note_count == 1
        assert metrics["commit_count"] == 1
        created = [combat_store.get_combatant("linden-pass", row_id) for row_id in receipt.created_combatant_ids]
        assert created[0].character_slug == "arden-march"
        assert created[0].current_hp == 17 and created[0].temp_hp == 5
        assert [row.source_kind for row in created] == [
            "character", "dm_statblock", "systems_monster", "manual_npc"
        ]
        assert len(combat_store.list_resource_counters(
            "linden-pass", combatant_ids=list(receipt.created_combatant_ids)
        )) == 1
        assert len(combat_store.list_resource_notes(
            "linden-pass", combatant_ids=list(receipt.created_combatant_ids)
        )) == 1


@pytest.mark.parametrize("failure_boundary", ["combatant", "counters", "notes", "revision", "audit"])
def test_apply_write_boundary_failures_roll_back_every_candidate_byte(
    app, monkeypatch, failure_boundary
):
    with app.app_context():
        service = _service(app)
        preset = service.create_preset(
            "linden-pass",
            name=f"Rollback {failure_boundary}",
            entries=(replace(_entry("First"), quantity=2),),
        )
        review = service.review_preset_apply("linden-pass", preset.id)
        connection = get_db()
        before = {
            table: tuple(tuple(row) for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall())
            for table in (
                "campaign_combat_trackers",
                "campaign_combatants",
                "campaign_combatant_resource_counters",
                "campaign_combatant_resource_notes",
                "auth_audit_log",
            )
        }
        combat_store = service.combat_store
        assert combat_store is not None
        if failure_boundary == "combatant":
            original = combat_store.create_combatant
            calls = 0

            def fail_second(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("injected combatant failure")
                return original(*args, **kwargs)

            monkeypatch.setattr(combat_store, "create_combatant", fail_second)
        elif failure_boundary == "counters":
            monkeypatch.setattr(combat_store, "create_resource_counters", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("injected counters failure")))
        elif failure_boundary == "notes":
            monkeypatch.setattr(combat_store, "create_resource_notes", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("injected notes failure")))
        elif failure_boundary == "revision":
            monkeypatch.setattr(combat_store, "bump_tracker_revision", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("injected revision failure")))
        else:
            original_audit = service.auth_store.insert_audit_event

            def fail_audit(**kwargs):
                original_audit(**kwargs)
                raise RuntimeError("injected audit failure")

            monkeypatch.setattr(service.auth_store, "insert_audit_event", fail_audit)

        with pytest.raises(RuntimeError, match="injected"):
            service.apply_preset(
                "linden-pass", preset.id, confirmation_digest=review.confirmation_digest
            )
        after = {
            table: tuple(tuple(row) for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall())
            for table in before
        }
        assert after == before


def test_post_commit_readback_failure_is_unconfirmed_without_rollback(app, monkeypatch):
    with app.app_context():
        service = _service(app)
        preset = service.create_preset(
            "linden-pass", name="Unconfirmed", entries=(_entry("Maybe Applied"),)
        )
        review = service.review_preset_apply("linden-pass", preset.id)
        combat_store = service.combat_store
        assert combat_store is not None
        original = combat_store.get_tracker

        def fail_after_commit(campaign_slug):
            if not get_db().in_transaction:
                raise RuntimeError("injected readback failure")
            return original(campaign_slug)

        monkeypatch.setattr(combat_store, "get_tracker", fail_after_commit)
        with pytest.raises(CampaignCombatPresetApplyOutcomeUnconfirmedError):
            service.apply_preset(
                "linden-pass", preset.id, confirmation_digest=review.confirmation_digest
            )

        monkeypatch.setattr(combat_store, "get_tracker", original)
        assert len(combat_store.list_combatants("linden-pass")) == 1
        assert _preset_events()[0].event_type == "campaign_encounter_preset_applied"


def test_empty_duplicate_and_existing_character_apply_reviews_fail_closed(app):
    with app.app_context():
        service = _service(app)
        assert app.extensions["character_repository"].get_visible_character(
            "linden-pass", "arden-march"
        ) is not None
        empty = service.create_preset("linden-pass", name="Empty", entries=())
        with pytest.raises(CampaignCombatPresetValidationError, match="empty"):
            service.review_preset_apply("linden-pass", empty.id)

        duplicate = service.create_preset(
            "linden-pass",
            name="Duplicate Character",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="character", source_ref="arden-march", quantity=2
            ),),
        )
        with pytest.raises(CampaignCombatPresetValidationError, match="only once"):
            service.review_preset_apply("linden-pass", duplicate.id)

        single = service.create_preset(
            "linden-pass",
            name="Existing Character",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="character", source_ref="arden-march"
            ),),
        )
        app.extensions["campaign_combat_service"].add_player_character(
            "linden-pass",
            character_slug="arden-march",
            created_by_user_id=app.config["TEST_USERS"]["dm"]["id"],
        )
        with pytest.raises(CampaignCombatPresetValidationError, match="already"):
            service.review_preset_apply("linden-pass", single.id)


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
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
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
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
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


class _NoResolverAccess:
    def __getattr__(self, _name):
        raise AssertionError("resolver accessed before authorization")


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
            combat_store=_NoStoreAccess(),
            authorization_adapter=lambda _slug: context,
            source_resolver=_NoResolverAccess(),
        )
        with pytest.raises(CampaignCombatPresetAuthorizationError):
            service.update_preset(
                "linden-pass",
                _ExplodingPayload(),
                expected_revision=_ExplodingPayload(),
                name=_ExplodingPayload(),
                entries=_ExplodingPayload(),
            )
        with pytest.raises(CampaignCombatPresetAuthorizationError):
            service.review_preset_apply("linden-pass", _ExplodingPayload())
        with pytest.raises(CampaignCombatPresetAuthorizationError):
            service.apply_preset(
                "linden-pass",
                _ExplodingPayload(),
                confirmation_digest=_ExplodingPayload(),
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
                source_resolver=_NoResolverAccess(),
            )
            with pytest.raises(CampaignCombatPresetAuthorizationError):
                service.get_preset("linden-pass", _ExplodingPayload())


def test_source_scope_and_apply_mutation_denials_precede_resolver_or_payload_access(app):
    with app.app_context():
        systems_denied = CampaignCombatPresetService(
            _NoStoreAccess(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(
                app.config["TEST_USERS"]["dm"]["id"],
                can_access_systems=False,
            ),
            source_resolver=_NoResolverAccess(),
        )
        with pytest.raises(CampaignCombatPresetAuthorizationError):
            systems_denied.create_preset(
                "linden-pass",
                name="Denied",
                entries=(
                    CampaignCombatPresetEntryInput(
                        source_kind="systems_monster",
                        source_ref="monster|MM|hidden",
                    ),
                ),
            )

        view_as = CampaignCombatPresetService(
            _NoStoreAccess(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(
                app.config["TEST_USERS"]["admin"]["id"],
                is_view_as=True,
                is_read_only=True,
            ),
            source_resolver=_NoResolverAccess(),
        )
        with pytest.raises(CampaignCombatPresetAuthorizationError):
            view_as.resolve_entries_for_apply("linden-pass", _ExplodingPayload())


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
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
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


def test_source_semantics_reject_before_the_accepted_store_boundary(app):
    class SemanticBoundaryStore:
        def __getattr__(self, _name):
            raise AssertionError("invalid source reached store")

    with app.app_context():
        service = CampaignCombatPresetService(
            SemanticBoundaryStore(),
            AuthStore(),
            authorization_adapter=lambda _slug: _context(
                app.config["TEST_USERS"]["dm"]["id"]
            ),
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
        )
        with pytest.raises(CampaignCombatPresetValidationError, match="source kind"):
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
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
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
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
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
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
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


def test_character_save_ignores_client_versions_and_inspect_apply_are_read_only(app):
    with app.app_context():
        connection = get_db()
        assert app.extensions["character_repository"].get_visible_character(
            "linden-pass",
            "arden-march",
        ) is not None
        connection.execute(
            "INSERT INTO campaign_combat_trackers "
            "(campaign_slug, round_number, revision, updated_at) VALUES (?, ?, ?, ?)",
            ("linden-pass", 3, 9, "unchanged"),
        )
        connection.commit()
        tracker_before = tuple(
            connection.execute(
                "SELECT * FROM campaign_combat_trackers WHERE campaign_slug = ?",
                ("linden-pass",),
            ).fetchone()
        )
        state_before = tuple(
            connection.execute(
                "SELECT * FROM character_state WHERE campaign_slug = ? ORDER BY character_slug",
                ("linden-pass",),
            ).fetchall()
        )
        character_state = app.extensions["character_state_store"].get_state(
            "linden-pass",
            "arden-march",
        )
        assert character_state is not None
        expected_vitals = dict(character_state.state.get("vitals") or {})
        definition_path = (
            app.config["TEST_CAMPAIGNS_DIR"]
            / "linden-pass"
            / "characters"
            / "arden-march"
            / "definition.yaml"
        )
        import_path = definition_path.with_name("import.yaml")
        source_bytes_before = (definition_path.read_bytes(), import_path.read_bytes())
        service = _service(app)
        created = service.create_preset(
            "linden-pass",
            name="Character Source",
            entries=(
                CampaignCombatPresetEntryInput(
                    source_kind="character",
                    source_ref="arden-march",
                    source_version="f" * 64,
                    version_scheme="client-scheme",
                    quantity=2,
                ),
            ),
        )
        saved = created.entries[0]
        assert saved.source_version != "f" * 64
        assert saved.version_scheme == "combat-seed-v1-sha256"

        reset_db_query_metrics()
        inspection = service.inspect_entries("linden-pass", created.entries)
        inspected_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        materialized = service.resolve_entries_for_apply(
            "linden-pass",
            created.entries,
        )
        applied_metrics = get_db_query_metrics()

        assert inspection[0].status == "current"
        assert len(materialized) == 2
        assert all(
            seed.current_hp == int(expected_vitals.get("current_hp") or 0)
            and seed.temp_hp == int(expected_vitals.get("temp_hp") or 0)
            for seed in materialized
        )
        assert inspected_metrics["write_count"] == 0
        assert applied_metrics["write_count"] == 0
        assert tuple(
            connection.execute(
                "SELECT * FROM campaign_combat_trackers WHERE campaign_slug = ?",
                ("linden-pass",),
            ).fetchone()
        ) == tracker_before
        assert tuple(
            connection.execute(
                "SELECT * FROM character_state WHERE campaign_slug = ? ORDER BY character_slug",
                ("linden-pass",),
            ).fetchall()
        ) == state_before
        assert (definition_path.read_bytes(), import_path.read_bytes()) == source_bytes_before


def test_apply_rejects_character_drift_without_adopting_or_mutating_tracker(app):
    with app.app_context():
        service = _service(app)
        assert app.extensions["character_repository"].get_visible_character(
            "linden-pass",
            "arden-march",
        ) is not None
        created = service.create_preset(
            "linden-pass",
            name="Drift Guard",
            entries=(
                CampaignCombatPresetEntryInput(
                    source_kind="character",
                    source_ref="arden-march",
                ),
            ),
        )
        review = service.review_preset_apply("linden-pass", created.id)
        connection = get_db()
        tracker_before = connection.execute(
            "SELECT COUNT(*) FROM campaign_combatants WHERE campaign_slug = ?",
            ("linden-pass",),
        ).fetchone()[0]
        definition_path = (
            app.config["TEST_CAMPAIGNS_DIR"]
            / "linden-pass"
            / "characters"
            / "arden-march"
            / "definition.yaml"
        )
        payload = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
        payload["name"] = "Changed Name"
        definition_path.write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
        app.extensions["character_repository"].invalidate_character(
            "linden-pass",
            "arden-march",
        )

        with pytest.raises(CampaignCombatPresetValidationError, match="changed"):
            service.resolve_entries_for_apply("linden-pass", created.entries)
        with pytest.raises(CampaignCombatPresetValidationError, match="changed"):
            service.apply_preset(
                "linden-pass",
                created.id,
                confirmation_digest=review.confirmation_digest,
            )

        assert CampaignCombatPresetStore().get_preset(
            "linden-pass",
            created.id,
        ) == created
        assert connection.execute(
            "SELECT COUNT(*) FROM campaign_combatants WHERE campaign_slug = ?",
            ("linden-pass",),
        ).fetchone()[0] == tracker_before


def test_apply_confirmation_binds_preset_revision_authorization_and_character_state(app):
    with app.app_context():
        actor = app.config["TEST_USERS"]["dm"]["id"]
        service = _service(app)
        manual = service.create_preset(
            "linden-pass", name="Revision Bound", entries=(_entry("Bound"),)
        )
        manual_review = service.review_preset_apply("linden-pass", manual.id)
        service.update_preset(
            "linden-pass",
            manual.id,
            expected_revision=manual.revision,
            name="Revision Changed",
            entries=manual.entries,
        )
        with pytest.raises(CampaignCombatPresetApplyConflictError):
            service.apply_preset(
                "linden-pass",
                manual.id,
                confirmation_digest=manual_review.confirmation_digest,
            )

        assert app.extensions["character_repository"].get_visible_character(
            "linden-pass", "arden-march"
        ) is not None
        character_preset = service.create_preset(
            "linden-pass",
            name="Vitals Bound",
            entries=(CampaignCombatPresetEntryInput(
                source_kind="character", source_ref="arden-march"
            ),),
        )
        character_review = service.review_preset_apply(
            "linden-pass", character_preset.id
        )
        record = app.extensions["character_repository"].get_visible_character(
            "linden-pass", "arden-march"
        )
        assert record is not None
        current_hp = int(dict(record.state_record.state.get("vitals") or {}).get("current_hp") or 0)
        app.extensions["character_state_service"].update_vitals(
            record,
            expected_revision=record.state_record.revision,
            current_hp=max(0, current_hp - 1),
            updated_by_user_id=actor,
        )
        with pytest.raises(CampaignCombatPresetApplyConflictError):
            service.apply_preset(
                "linden-pass",
                character_preset.id,
                confirmation_digest=character_review.confirmation_digest,
            )

        mutable_context = {"value": _context(actor)}
        authorization_service = CampaignCombatPresetService(
            CampaignCombatPresetStore(),
            AuthStore(),
            combat_store=app.extensions["campaign_combat_store"],
            authorization_adapter=lambda _slug: mutable_context["value"],
            source_resolver=app.extensions["campaign_combat_preset_source_resolver"],
        )
        authorization_preset = authorization_service.create_preset(
            "linden-pass", name="Authorization Bound", entries=(_entry("Auth"),)
        )
        authorization_review = authorization_service.review_preset_apply(
            "linden-pass", authorization_preset.id
        )
        mutable_context["value"] = _context(app.config["TEST_USERS"]["admin"]["id"])
        with pytest.raises(CampaignCombatPresetApplyConflictError):
            authorization_service.apply_preset(
                "linden-pass",
                authorization_preset.id,
                confirmation_digest=authorization_review.confirmation_digest,
            )

        assert app.extensions["campaign_combat_store"].list_combatants("linden-pass") == []


def test_systems_inspection_never_seeds_absent_or_incomplete_library_rows(app):
    saved = CampaignCombatPresetEntryInput(
        source_kind="systems_monster",
        source_ref="monster|MM|missing",
        source_version="0" * 64,
        version_scheme="combat-seed-v1-sha256",
    )
    with app.app_context():
        service = _service(app)
        connection = get_db()

        def inventory():
            return tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "systems_libraries",
                    "systems_sources",
                    "systems_entries",
                    "campaign_enabled_sources",
                    "campaign_entry_overrides",
                )
            )

        absent_before = inventory()
        reset_db_query_metrics()
        absent = service.inspect_entries("linden-pass", (saved,))
        absent_metrics = get_db_query_metrics()
        assert absent[0].status == "missing_or_inaccessible"
        assert inventory() == absent_before
        assert absent_metrics["write_count"] == 0

        app.extensions["systems_store"].upsert_library(
            "dnd-5e",
            title="Incomplete",
            system_code="DND-5E",
        )
        incomplete_before = inventory()
        reset_db_query_metrics()
        incomplete = service.inspect_entries("linden-pass", (saved,))
        incomplete_metrics = get_db_query_metrics()
        assert incomplete[0].status == "missing_or_inaccessible"
        assert inventory() == incomplete_before
        assert incomplete_metrics["write_count"] == 0


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
        source_resolver=object(),
    )
    assert isinstance(service, CampaignCombatPresetService)
