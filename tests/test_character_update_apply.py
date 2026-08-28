from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from copy import deepcopy
from pathlib import Path
from threading import Barrier, Lock
from time import perf_counter

import pytest

from player_wiki.character_update_apply import (
    CharacterUpdateApplyClassification,
    CharacterUpdateRecompute,
    CharacterUpdateReviewClaims,
    CharacterUpdateTokenCodec,
    CharacterUpdateTokenError,
)
from player_wiki.character_models import CharacterDefinition, CharacterImportMetadata
from player_wiki.character_reconciliation import (
    CharacterPublicationCoordinator,
    CharacterReconciliationHooks,
)
from player_wiki.character_repository import load_campaign_character_config
from player_wiki.character_service import build_initial_state
from player_wiki.character_update_planner import (
    ChangeKind,
    CharacterUpdatePlan,
    PlanStatus,
    ResourceAddition,
    SemanticCategory,
    SemanticDiffRow,
    StateImpact,
    StateReconciliation,
)
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics


def _claims(**overrides) -> CharacterUpdateReviewClaims:
    payload = {
        "actor_user_id": 17,
        "campaign_slug": "linden-pass",
        "character_slug": "arden-march",
        "operations": (
            {
                "kind": "campaign_feature_grant",
                "source_kind": "campaign_page",
                "source_value": "mechanics/harbor-blessing",
                "target_id": "campaign-feature-mechanics-harbor-blessing",
                "quantity": 1,
            },
        ),
        "definition_digest": "a" * 64,
        "import_digest": "b" * 64,
        "state_revision": 7,
        "state_digest": "c" * 64,
        "state_updated_at": "2026-08-28T12:00:00+00:00",
        "state_updated_by_user_id": 11,
        "source_digest": "d" * 64,
        "policy_digest": "e" * 64,
        "native_digest": "f" * 64,
        "planner_version": 1,
        "state_impact": "preserve_exact",
        "candidate_digest": "1" * 64,
        "semantic_digest": "2" * 64,
        "issued_at": 1_788_000_000,
    }
    payload.update(overrides)
    return CharacterUpdateReviewClaims(**payload)


def test_cu1_token_is_canonical_bounded_actor_target_bound_and_expires_at_ten_minutes():
    codec = CharacterUpdateTokenCodec("test-secret", now=lambda: 1_788_000_000)
    claims = _claims()

    token = codec.issue(claims)

    assert token.startswith("cu1.")
    assert len(token.encode("utf-8")) <= 8 * 1024
    assert codec.verify(
        token,
        actor_user_id=17,
        campaign_slug="linden-pass",
        character_slug="arden-march",
        now=1_788_000_600,
    ) == claims

    with pytest.raises(CharacterUpdateTokenError):
        codec.verify(
            token,
            actor_user_id=17,
            campaign_slug="linden-pass",
            character_slug="arden-march",
            now=1_788_000_601,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor_user_id", 18),
        ("campaign_slug", "other-campaign"),
        ("character_slug", "other-character"),
    ],
)
def test_cu1_token_refuses_actor_and_target_substitution(field, value):
    codec = CharacterUpdateTokenCodec("test-secret", now=lambda: 1_788_000_000)
    token = codec.issue(_claims())
    arguments = {
        "actor_user_id": 17,
        "campaign_slug": "linden-pass",
        "character_slug": "arden-march",
        "now": 1_788_000_001,
    }
    arguments[field] = value

    with pytest.raises(CharacterUpdateTokenError):
        codec.verify(token, **arguments)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda token: token[:-1] + ("A" if token[-1] != "A" else "B"),
        lambda token: token.replace("cu1.", "cu2.", 1),
        lambda token: token + "=",
        lambda token: token.rsplit(".", 1)[0],
    ],
)
def test_cu1_token_refuses_signature_prefix_and_encoding_adversaries(mutator):
    codec = CharacterUpdateTokenCodec("test-secret", now=lambda: 1_788_000_000)
    token = codec.issue(_claims())

    with pytest.raises(CharacterUpdateTokenError):
        codec.verify(
            mutator(token),
            actor_user_id=17,
            campaign_slug="linden-pass",
            character_slug="arden-march",
            now=1_788_000_001,
        )


def test_cu1_token_rejects_oversize_instead_of_truncating():
    codec = CharacterUpdateTokenCodec("test-secret", now=lambda: 1_788_000_000)
    oversized = replace(
        _claims(),
        operations=(
            {
                "kind": "campaign_feature_grant",
                "source_kind": "campaign_page",
                "source_value": "x" * 7600,
                "target_id": "campaign-feature-x",
                "quantity": 1,
            },
        ),
    )

    with pytest.raises(CharacterUpdateTokenError):
        codec.issue(oversized)


def test_cu1_token_accepts_exactly_128_operations_within_batch_bound_and_rejects_129():
    codec = CharacterUpdateTokenCodec("test-secret", now=lambda: 1_788_000_000)
    operations = tuple(
        {
            "kind": "campaign_feature_grant",
            "source_kind": "campaign_page",
            "source_value": f"mechanics/grant-{index}",
            "target_id": f"campaign-feature-grant-{index}",
            "quantity": 1,
        }
        for index in range(128)
    )

    token = codec.issue(replace(_claims(), operations=operations))

    assert len(token.encode("utf-8")) <= 384 * 1024
    assert len(
        codec.verify(
            token,
            actor_user_id=17,
            campaign_slug="linden-pass",
            character_slug="arden-march",
        ).operations
    ) == 128
    with pytest.raises(CharacterUpdateTokenError):
        codec.issue(replace(_claims(), operations=operations + (operations[0],)))


def _definition(slug: str) -> CharacterDefinition:
    return CharacterDefinition.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": slug,
            "name": "Apply Test",
            "status": "active",
            "system": "DND-5E",
            "profile": {},
            "stats": {},
            "skills": [],
            "proficiencies": {},
            "attacks": [],
            "features": [],
            "spellcasting": {},
            "equipment_catalog": [],
            "reference_notes": {},
            "resource_templates": [],
            "source": {"source_path": f"test://{slug}"},
        }
    )


def _metadata(slug: str) -> CharacterImportMetadata:
    return CharacterImportMetadata.from_dict(
        {
            "campaign_slug": "linden-pass",
            "character_slug": slug,
            "source_path": f"test://{slug}",
            "imported_at_utc": "2026-08-28T00:00:00Z",
            "parser_version": "test",
            "import_status": "clean",
            "warnings": [],
        }
    )


def _recompute(record, *, status=PlanStatus.READY, candidate=None):
    candidate_payload = deepcopy(candidate or record.definition.to_dict())
    plan = CharacterUpdatePlan(
        1,
        "linden-pass/apply-test",
        f"character-state-revision-{record.state_record.revision}",
        status,
        (),
        StateImpact.PRESERVE_EXACT,
        StateReconciliation(),
        (),
        "1" * 64,
        candidate_payload,
        {**candidate_payload, "state": deepcopy(record.state_record.state)},
        (),
    )
    return CharacterUpdateRecompute(
        record=record,
        plan=plan,
        operations=_claims().operations,
        source_digest="d" * 64,
        policy_digest="e" * 64,
        native_digest="f" * 64,
        readback_semantic_rows=lambda _record: (),
    )


def test_ready_apply_calls_coordinator_once_preserves_exact_state_audits_once_and_replay_refuses(
    app,
    monkeypatch,
    record_property,
):
    engine = app.extensions["character_update_apply_engine"]
    coordinator = engine.coordinator
    definition = _definition("apply-test")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = coordinator.create(
            definition,
            _metadata("apply-test"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        candidate = deepcopy(record.definition.to_dict())
        candidate["name"] = "Applied Exactly Once"
        recomputed = _recompute(record, candidate=candidate)
        readback_calls = 0

        def readback_once(_record):
            nonlocal readback_calls
            readback_calls += 1
            return ()

        recomputed = replace(recomputed, readback_semantic_rows=readback_once)
        issued = engine.issue_review(recomputed, actor_user_id=actor_user_id)
        assert issued.token is not None
        before_state = engine.state_store.get_exact_state("linden-pass", "apply-test")
        calls = 0
        publication_calls = 0
        statements: list[str] = []
        original_update = coordinator.update
        original_publish = coordinator._publish_file
        original_path_open = Path.open
        campaign_reads = 0

        def counted_update(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original_update(*args, **kwargs)

        def counted_publish(*args, **kwargs):
            nonlocal publication_calls
            publication_calls += 1
            return original_publish(*args, **kwargs)

        def counted_path_open(path, mode="r", *args, **kwargs):
            nonlocal campaign_reads
            try:
                within_campaigns = engine.campaigns_dir.resolve() in path.resolve().parents
            except OSError:
                within_campaigns = False
            if within_campaigns and "r" in mode:
                campaign_reads += 1
            return original_path_open(path, mode, *args, **kwargs)

        monkeypatch.setattr(coordinator, "update", counted_update)
        monkeypatch.setattr(coordinator, "_publish_file", counted_publish)
        monkeypatch.setattr(Path, "open", counted_path_open)
        get_db().set_trace_callback(statements.append)
        reset_db_query_metrics()
        started = perf_counter()
        result = engine.apply(
            issued.token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug="apply-test",
            recompute=lambda operations: (
                recomputed if operations == recomputed.operations else pytest.fail("operations drift")
            ),
        )
        elapsed_ms = (perf_counter() - started) * 1000
        query_metrics = get_db_query_metrics()
        get_db().set_trace_callback(None)

        assert result.classification is CharacterUpdateApplyClassification.CONFIRMED_APPLIED
        assert calls == 1
        assert publication_calls == 2
        assert readback_calls == 1
        assert query_metrics["query_count"] <= 96
        assert campaign_reads <= 32
        assert elapsed_ms <= 500
        record_property("single_apply_ms", elapsed_ms)
        record_property("single_apply_queries", query_metrics["query_count"])
        record_property("single_apply_reads", campaign_reads)
        record_property("single_apply_token_bytes", len(issued.token.encode("utf-8")))
        structural_writes = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith(
                (
                    "INSERT INTO CHARACTER_RECONCILIATION_OPERATIONS",
                    "UPDATE CHARACTER_RECONCILIATION_OPERATIONS",
                    "DELETE FROM CHARACTER_RECONCILIATION_OPERATIONS",
                    "UPDATE CHARACTER_STATE",
                    "INSERT INTO AUTH_AUDIT_LOG",
                )
            )
        ]
        assert len(structural_writes) == 4
        assert not any("UPDATE CHARACTER_STATE" in row.upper() for row in structural_writes)
        assert engine.state_store.get_exact_state("linden-pass", "apply-test") == before_state
        audit_rows = get_db().execute(
            """SELECT event_type, actor_user_id, campaign_slug, character_slug, metadata_json
            FROM auth_audit_log WHERE event_type = 'character_update_applied'"""
        ).fetchall()
        assert len(audit_rows) == 1
        assert audit_rows[0]["actor_user_id"] == actor_user_id

        replay = engine.apply(
            issued.token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug="apply-test",
            recompute=lambda _operations: _recompute(
                coordinator.repository.get_combat_seed_character(
                    "linden-pass", "apply-test"
                ),
                status=PlanStatus.NO_OP,
            ),
        )
        assert replay.classification is CharacterUpdateApplyClassification.REFUSED_STALE
        assert calls == 1


def test_no_op_review_is_unchanged_without_token_or_coordinator_call(app, monkeypatch):
    engine = app.extensions["character_update_apply_engine"]
    definition = _definition("no-op-test")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = engine.coordinator.create(
            definition,
            _metadata("no-op-test"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        monkeypatch.setattr(
            engine.coordinator,
            "update",
            lambda *_args, **_kwargs: pytest.fail("NO_OP cannot call coordinator"),
        )
        statements: list[str] = []
        get_db().set_trace_callback(statements.append)
        issue = engine.issue_review(
            _recompute(record, status=PlanStatus.NO_OP),
            actor_user_id=actor_user_id,
        )
        get_db().set_trace_callback(None)

        assert issue.token is None
        assert issue.classification is CharacterUpdateApplyClassification.UNCHANGED
        assert not any(
            statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            for statement in statements
        )


@pytest.mark.parametrize(
    "dimension",
    (
        "source",
        "policy",
        "native",
        "planner",
        "candidate",
        "semantic",
        "operations",
        "state",
        "definition_file",
        "import_file",
    ),
)
def test_every_review_attestation_drift_refuses_before_coordinator(
    app,
    monkeypatch,
    dimension,
):
    engine = app.extensions["character_update_apply_engine"]
    definition = _definition(f"drift-{dimension}")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = engine.coordinator.create(
            definition,
            _metadata(f"drift-{dimension}"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        current = _recompute(record)
        token = engine.issue_review(current, actor_user_id=actor_user_id).token
        assert token is not None
        if dimension == "source":
            current = replace(current, source_digest="3" * 64)
        elif dimension == "policy":
            current = replace(current, policy_digest="3" * 64)
        elif dimension == "native":
            current = replace(current, native_digest="3" * 64)
        elif dimension == "planner":
            current = replace(current, plan=replace(current.plan, version=2))
        elif dimension == "candidate":
            current = replace(current, plan=replace(current.plan, digest="3" * 64))
        elif dimension == "semantic":
            current = replace(
                current,
                plan=replace(
                    current.plan,
                    semantic_diff=(
                        SemanticDiffRow(
                            SemanticCategory.FEATURES,
                            "name",
                            "Name",
                            ChangeKind.UPDATED,
                            "Before",
                            "After",
                        ),
                    ),
                ),
            )
        elif dimension == "operations":
            changed = dict(current.operations[0])
            changed["source_value"] = "mechanics/changed"
            current = replace(current, operations=(changed,))
        elif dimension == "state":
            get_db().execute(
                """UPDATE character_state SET updated_at = 'changed-after-review'
                WHERE campaign_slug = 'linden-pass' AND character_slug = ?""",
                (f"drift-{dimension}",),
            )
            get_db().commit()
        else:
            config = load_campaign_character_config(
                app.config["CAMPAIGNS_DIR"], "linden-pass"
            )
            filename = "definition.yaml" if dimension == "definition_file" else "import.yaml"
            path = config.characters_dir / f"drift-{dimension}" / filename
            path.write_bytes(path.read_bytes() + b"\n")

        monkeypatch.setattr(
            engine.coordinator,
            "update",
            lambda *_args, **_kwargs: pytest.fail("drift cannot cross coordinator boundary"),
        )
        result = engine.apply(
            token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug=f"drift-{dimension}",
            recompute=lambda _operations: current,
        )

        assert result.classification is CharacterUpdateApplyClassification.REFUSED_STALE


def test_reconcile_apply_adds_only_reviewed_row_advances_once_and_stays_within_five_writes(
    app,
    monkeypatch,
):
    engine = app.extensions["character_update_apply_engine"]
    coordinator = engine.coordinator
    definition = _definition("reconcile-test")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = coordinator.create(
            definition,
            _metadata("reconcile-test"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        candidate = deepcopy(record.definition.to_dict())
        template = {
            "id": "resource:ember",
            "label": "Ember",
            "category": "custom_progress",
            "max": 2,
            "initial_current": 2,
        }
        candidate["resource_templates"] = [template]
        desired_state = deepcopy(record.state_record.state)
        desired_state["resources"].append(
            {
                "id": "resource:ember",
                "label": "Ember",
                "category": "custom_progress",
                "current": 2,
                "max": 2,
                "reset_on": "manual",
                "reset_to": "unchanged",
                "rest_behavior": "manual_only",
                "notes": "",
                "display_order": 0,
            }
        )
        recomputed = _recompute(record, candidate=candidate)
        recomputed = replace(
            recomputed,
            plan=replace(
                recomputed.plan,
                state_impact=StateImpact.RECONCILE_REQUIRED,
                reconciliation=StateReconciliation(
                    (ResourceAddition("resource:ember", 2, "Ember"),)
                ),
                derived_character={**candidate, "state": desired_state},
            ),
        )
        token = engine.issue_review(recomputed, actor_user_id=actor_user_id).token
        assert token is not None
        before_state = engine.state_store.get_exact_state("linden-pass", "reconcile-test")
        publication_calls = 0
        original_publish = coordinator._publish_file

        def counted_publish(*args, **kwargs):
            nonlocal publication_calls
            publication_calls += 1
            return original_publish(*args, **kwargs)

        monkeypatch.setattr(coordinator, "_publish_file", counted_publish)
        statements: list[str] = []
        get_db().set_trace_callback(statements.append)
        result = engine.apply(
            token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug="reconcile-test",
            recompute=lambda _operations: recomputed,
        )
        get_db().set_trace_callback(None)

        assert result.classification is CharacterUpdateApplyClassification.CONFIRMED_APPLIED
        after_state = engine.state_store.get_exact_state("linden-pass", "reconcile-test")
        assert before_state is not None and after_state is not None
        assert after_state.revision == before_state.revision + 1
        assert after_state.state["resources"][:-1] == before_state.state["resources"]
        assert after_state.state["resources"][-1]["id"] == "resource:ember"
        assert after_state.state["inventory"] == before_state.state["inventory"]
        assert publication_calls == 2
        structural_writes = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith(
                (
                    "INSERT INTO CHARACTER_RECONCILIATION_OPERATIONS",
                    "UPDATE CHARACTER_RECONCILIATION_OPERATIONS",
                    "DELETE FROM CHARACTER_RECONCILIATION_OPERATIONS",
                    "UPDATE CHARACTER_STATE",
                    "INSERT INTO AUTH_AUDIT_LOG",
                )
            )
        ]
        assert len(structural_writes) == 5
        assert sum("UPDATE CHARACTER_STATE" in row.upper() for row in structural_writes) == 1


def test_128_operation_apply_stays_within_query_read_readback_and_time_ceilings(
    app,
    monkeypatch,
    record_property,
):
    engine = app.extensions["character_update_apply_engine"]
    definition = _definition("batch-apply")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = engine.coordinator.create(
            definition,
            _metadata("batch-apply"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        candidate = deepcopy(record.definition.to_dict())
        candidate["name"] = "Batch Applied"
        operations = tuple(
            {
                "kind": "campaign_feature_grant",
                "source_kind": "campaign_page",
                "source_value": f"mechanics/batch-{index}",
                "target_id": f"campaign-feature-batch-{index}",
                "quantity": 1,
            }
            for index in range(128)
        )
        readback_calls = 0

        def readback_once(_record):
            nonlocal readback_calls
            readback_calls += 1
            return ()

        recomputed = replace(
            _recompute(record, candidate=candidate),
            operations=operations,
            readback_semantic_rows=readback_once,
        )
        token = engine.issue_review(recomputed, actor_user_id=actor_user_id).token
        assert token is not None
        assert len(token.encode("utf-8")) <= 384 * 1024
        original_path_open = Path.open
        campaign_reads = 0

        def counted_path_open(path, mode="r", *args, **kwargs):
            nonlocal campaign_reads
            try:
                within_campaigns = engine.campaigns_dir.resolve() in path.resolve().parents
            except OSError:
                within_campaigns = False
            if within_campaigns and "r" in mode:
                campaign_reads += 1
            return original_path_open(path, mode, *args, **kwargs)

        monkeypatch.setattr(Path, "open", counted_path_open)
        reset_db_query_metrics()
        started = perf_counter()
        result = engine.apply(
            token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug="batch-apply",
            recompute=lambda reviewed: (
                recomputed if reviewed == operations else pytest.fail("operations drift")
            ),
        )
        elapsed_ms = (perf_counter() - started) * 1000
        metrics = get_db_query_metrics()

        assert result.classification is CharacterUpdateApplyClassification.CONFIRMED_APPLIED
        assert metrics["query_count"] <= 96
        assert campaign_reads <= 32
        assert readback_calls == 1
        assert elapsed_ms <= 2500
        record_property("batch_apply_ms", elapsed_ms)
        record_property("batch_apply_queries", metrics["query_count"])
        record_property("batch_apply_reads", campaign_reads)
        record_property("batch_apply_token_bytes", len(token.encode("utf-8")))


def test_apply_recomputes_once_and_classifies_pre_and_post_boundary_failures(app, monkeypatch):
    engine = app.extensions["character_update_apply_engine"]
    definition = _definition("classification-test")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = engine.coordinator.create(
            definition,
            _metadata("classification-test"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        recomputed = _recompute(record)
        token = engine.issue_review(recomputed, actor_user_id=actor_user_id).token
        assert token is not None
        calls = 0

        def failed_recompute(_operations):
            nonlocal calls
            calls += 1
            return replace(recomputed, plan=replace(recomputed.plan, candidate_definition=None))

        failed = engine.apply(
            token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug="classification-test",
            recompute=failed_recompute,
        )
        assert failed.classification is CharacterUpdateApplyClassification.FAILED
        assert calls == 1

        monkeypatch.setattr(
            engine.coordinator,
            "update",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("post-boundary")),
        )
        uncertain = engine.apply(
            token,
            actor_user_id=actor_user_id,
            campaign_slug="linden-pass",
            character_slug="classification-test",
            recompute=lambda _operations: recomputed,
        )
        assert uncertain.classification is CharacterUpdateApplyClassification.UNCERTAIN


def test_concurrent_use_of_one_review_token_mutates_and_audits_only_once(app, monkeypatch):
    engine = app.extensions["character_update_apply_engine"]
    definition = _definition("concurrent-apply")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        record = engine.coordinator.create(
            definition,
            _metadata("concurrent-apply"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        candidate = deepcopy(record.definition.to_dict())
        candidate["name"] = "Concurrent Winner"
        recomputed = _recompute(record, candidate=candidate)
        token = engine.issue_review(recomputed, actor_user_id=actor_user_id).token
        assert token is not None

    barrier = Barrier(2)
    count_lock = Lock()
    coordinator_calls = 0
    original_update = engine.coordinator.update

    def synchronized_update(*args, **kwargs):
        nonlocal coordinator_calls
        with count_lock:
            coordinator_calls += 1
        barrier.wait(timeout=10)
        return original_update(*args, **kwargs)

    monkeypatch.setattr(engine.coordinator, "update", synchronized_update)

    def apply_once():
        with app.app_context():
            return engine.apply(
                token,
                actor_user_id=actor_user_id,
                campaign_slug="linden-pass",
                character_slug="concurrent-apply",
                recompute=lambda _operations: recomputed,
            ).classification

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _index: apply_once(), range(2)))

    assert set(outcomes) == {
        CharacterUpdateApplyClassification.CONFIRMED_APPLIED,
        CharacterUpdateApplyClassification.UNCERTAIN,
    }
    assert coordinator_calls == 2
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'character_update_applied'"
        ).fetchone()[0] == 1


def test_journal_backed_apply_audit_is_inserted_once_before_repository_pending_recovery(app):
    engine = app.extensions["character_update_apply_engine"]
    definition = _definition("audit-recovery")
    with app.app_context():
        actor_user_id = int(get_db().execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0])
        prior = engine.coordinator.create(
            definition,
            _metadata("audit-recovery"),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        desired_payload = deepcopy(prior.definition.to_dict())
        desired_payload["name"] = "Audit Recovery"

        def crash(event: str, _operation_id: str) -> None:
            if event == "after_repository_pending":
                raise RuntimeError("injected post-boundary crash")

        crashing = CharacterPublicationCoordinator(
            campaigns_dir=app.config["CAMPAIGNS_DIR"],
            database_path=app.config["DB_PATH"],
            state_store=engine.state_store,
            repository=engine.coordinator.repository,
            auth_store=app.extensions["auth_store"],
            hooks=CharacterReconciliationHooks(on_event=crash),
        )
        with pytest.raises(RuntimeError, match="post-boundary"):
            crashing.update(
                prior,
                CharacterDefinition.from_dict(desired_payload),
                prior.import_metadata,
                deepcopy(prior.state_record.state),
                expected_revision=prior.state_record.revision,
                updated_by_user_id=actor_user_id,
                operation_kind="character_update_apply",
                audit_event_type="character_update_applied",
                audit_actor_user_id=actor_user_id,
                audit_metadata={
                    "source": "character_update_preview",
                    "review_digest": "4" * 64,
                },
            )
        journal = get_db().execute(
            """SELECT state, audit_event_type, audit_actor_user_id, audit_metadata_json
            FROM character_reconciliation_operations
            WHERE character_slug = 'audit-recovery'"""
        ).fetchone()
        assert tuple(journal)[:3] == (
            "repository_pending",
            "character_update_applied",
            actor_user_id,
        )
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'character_update_applied'"
        ).fetchone()[0] == 1

        assert engine.coordinator.recover_key("linden-pass", "audit-recovery") is True
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'character_update_applied'"
        ).fetchone()[0] == 1
        assert get_db().execute(
            "SELECT 1 FROM character_reconciliation_operations WHERE character_slug = 'audit-recovery'"
        ).fetchone() is None


@pytest.mark.parametrize(
    ("journal_state", "expected_recovered", "expected_audits"),
    [
        ("prepared", True, 1),
        ("repository_pending", True, 1),
        ("conflict", False, 0),
    ],
)
def test_deleted_apply_actor_recovery_is_truthful_and_idempotent(
    app, journal_state, expected_recovered, expected_audits
):
    engine = app.extensions["character_update_apply_engine"]
    character_slug = f"deleted-actor-{journal_state.replace('_', '-')}"
    definition = _definition(character_slug)
    with app.app_context():
        actor_user_id = app.extensions["auth_store"].create_user(
            f"deleted-apply-{journal_state}@example.test",
            f"Deleted Apply {journal_state}",
            status="active",
        ).id
        prior = engine.coordinator.create(
            definition,
            _metadata(character_slug),
            build_initial_state(definition),
            operation_kind="native_create",
        )
        desired_payload = deepcopy(prior.definition.to_dict())
        desired_payload["name"] = f"Deleted Actor {journal_state}"
        stop_event = (
            "after_repository_pending"
            if journal_state == "repository_pending"
            else "after_commit"
        )

        def stop(event: str, _operation_id: str) -> None:
            if event == stop_event:
                raise RuntimeError("retain apply journal")

        crashing = CharacterPublicationCoordinator(
            campaigns_dir=app.config["CAMPAIGNS_DIR"],
            database_path=app.config["DB_PATH"],
            state_store=engine.state_store,
            repository=engine.coordinator.repository,
            auth_store=app.extensions["auth_store"],
            hooks=CharacterReconciliationHooks(on_event=stop),
        )
        with pytest.raises(RuntimeError, match="retain apply journal"):
            crashing.update(
                prior,
                CharacterDefinition.from_dict(desired_payload),
                prior.import_metadata,
                deepcopy(prior.state_record.state),
                expected_revision=prior.state_record.revision,
                updated_by_user_id=actor_user_id,
                operation_kind="character_update_apply",
                audit_event_type="character_update_applied",
                audit_actor_user_id=actor_user_id,
                audit_metadata={
                    "source": "character_update_preview",
                    "review_digest": "5" * 64,
                },
            )
        if journal_state == "conflict":
            get_db().execute(
                """UPDATE character_reconciliation_operations
                SET state = 'conflict', error_code = 'injected_conflict'
                WHERE character_slug = ?""",
                (character_slug,),
            )
            get_db().commit()

        if journal_state == "repository_pending":
            get_db().execute(
                "UPDATE auth_audit_log SET actor_user_id = NULL WHERE actor_user_id = ?",
                (actor_user_id,),
            )
            get_db().commit()

        get_db().execute("DELETE FROM users WHERE id = ?", (actor_user_id,))
        get_db().commit()
        journal = get_db().execute(
            """SELECT state, audit_event_type, audit_actor_user_id, audit_metadata_json
            FROM character_reconciliation_operations WHERE character_slug = ?""",
            (character_slug,),
        ).fetchone()
        assert journal["state"] == journal_state
        assert journal["audit_event_type"] == "character_update_applied"
        assert journal["audit_actor_user_id"] is None
        assert journal["audit_metadata_json"] is not None

        assert engine.coordinator.recover_key("linden-pass", character_slug) is expected_recovered
        assert engine.coordinator.recover_key("linden-pass", character_slug) is False
        assert get_db().execute(
            "SELECT COUNT(*) FROM auth_audit_log WHERE event_type = 'character_update_applied'"
        ).fetchone()[0] == expected_audits
        remaining = get_db().execute(
            "SELECT state FROM character_reconciliation_operations WHERE character_slug = ?",
            (character_slug,),
        ).fetchone()
        if journal_state == "conflict":
            assert remaining["state"] == "conflict"
        else:
            assert remaining is None
        assert get_db().execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert get_db().execute("PRAGMA foreign_key_check").fetchall() == []
