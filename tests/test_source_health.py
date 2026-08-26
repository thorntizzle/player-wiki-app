from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest
import yaml

import player_wiki.campaign_combat_store as campaign_combat_store_module
import player_wiki.campaign_page_store as campaign_page_store_module
import player_wiki.character_repository as character_repository_module
import player_wiki.systems_service as systems_service_module
from player_wiki.campaign_combat_store import CampaignCombatStore
from player_wiki.campaign_dm_content_store import CampaignDMContentStore
from player_wiki.campaign_page_store import CampaignPageStore
from player_wiki.character_path_safety import CharacterPathSafetyError
from player_wiki.db import get_db, get_db_query_metrics, reset_db_query_metrics
from player_wiki.source_health import (
    SOURCE_HEALTH_ACTIONS,
    SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES,
    SOURCE_HEALTH_CLASSIFICATIONS,
    SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES,
    SOURCE_HEALTH_SEVERITIES,
    SOURCE_HEALTH_TARGET_REFERENCE_LIMIT,
    SourceHealthAccessContext,
    SourceHealthBrowserCursorCodec,
    SourceHealthConsumer,
    SourceHealthCursorCodec,
    SourceHealthCursorError,
    SourceHealthDenied,
    SourceHealthFinding,
    SourceHealthInventoryPage,
    SourceHealthReference,
    SourceHealthResolution,
    SourceHealthReport,
    SourceHealthService,
    SourceHealthTarget,
    SourceHealthResolutionBatch,
    classify_source_health,
    mark_source_health_report_stale,
    serialize_source_health_report,
)
from player_wiki.systems_store import SystemsStore
from tests.sample_data import TEST_CAMPAIGN_SLUG


def _cursor_codec() -> SourceHealthCursorCodec:
    return SourceHealthCursorCodec(b"source-health-test-key-material-v1")


def _equivalent_noncanonical_b64_segment(segment: str) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    padding = "=" * (-len(segment) % 4)
    decoded = base64.b64decode(
        segment + padding,
        altchars=b"-_",
        validate=True,
    )
    for replacement in alphabet:
        candidate = f"{segment[:-1]}{replacement}"
        if candidate == segment:
            continue
        try:
            candidate_decoded = base64.b64decode(
                candidate + padding,
                altchars=b"-_",
                validate=True,
            )
        except ValueError:
            continue
        if candidate_decoded == decoded:
            return candidate
    raise AssertionError("Expected a noncanonical equivalent Base64 spelling.")


class _RecordingCursor:
    def __init__(self, cursor, record: dict[str, object]) -> None:
        self._cursor = cursor
        self._record = record

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)

    def fetchall(self):
        rows = self._cursor.fetchall()
        self._record["row_count"] = len(rows)
        if rows and "page_ref" in rows[0].keys():
            self._record["row_keys"] = [str(row["page_ref"]) for row in rows]
        elif rows and "id" in rows[0].keys():
            self._record["row_keys"] = [int(row["id"]) for row in rows]
        else:
            self._record["row_keys"] = []
        return rows


class _RecordingConnection:
    def __init__(self, connection) -> None:
        self._connection = connection
        self.records: list[dict[str, object]] = []

    def execute(self, sql: str, parameters=()):
        record: dict[str, object] = {
            "sql": " ".join(sql.split()),
            "parameters": tuple(parameters),
        }
        self.records.append(record)
        return _RecordingCursor(self._connection.execute(sql, parameters), record)


def _service(**kwargs) -> SourceHealthService:
    kwargs.setdefault(
        "character_resolver",
        lambda _context, references: SourceHealthResolutionBatch(
            resolutions={
                reference: SourceHealthResolution() for reference in references
            }
        ),
    )
    kwargs.setdefault("cursor_codec", _cursor_codec())
    return SourceHealthService(**kwargs)


def _reference(**overrides) -> SourceHealthReference:
    values = {
        "target_kind": "systems",
        "library_slug": "DND-5E",
        "entry_key": "spell|PHB|shield",
        "slug": "phb-shield",
        "source_id": "PHB",
        "consumer_version": "",
        "version_scheme": "",
    }
    values.update(overrides)
    return SourceHealthReference(**values)


def _consumer(**overrides) -> SourceHealthConsumer:
    values = {
        "consumer_type": "character",
        "consumer_key": "arden-march:spellcasting.spells[0]",
        "surface": "Character",
        "reference": _reference(),
        "accepted_target_types": ("spell",),
        "destination": "/campaigns/linden-pass/characters/arden-march",
    }
    values.update(overrides)
    return SourceHealthConsumer(**values)


def test_combat_seed_fingerprint_is_exact_equality_and_malformed_values_fail_closed():
    reference = SourceHealthReference(
        target_kind="character",
        target_id="hero",
        consumer_version="a" * 64,
        version_scheme="combat-seed-v1-sha256",
    )
    consumer = SourceHealthConsumer(
        consumer_type="encounter-preset-entry",
        consumer_key="opaque",
        surface="Encounter preset",
        reference=reference,
        accepted_target_types=("character",),
    )
    current = SourceHealthTarget(
        target_kind="character",
        canonical_identity="character:linden-pass:hero",
        target_type="character",
        target_version="b" * 64,
        version_scheme="combat-seed-v1-sha256",
        destination="/campaigns/linden-pass/characters/hero",
    )

    finding = classify_source_health(
        consumer,
        SourceHealthResolution(targets=(current,)),
    )
    assert finding.classification == "stale-version"
    assert finding.action == "inspect_source"

    with pytest.raises(ValueError):
        classify_source_health(
            replace(consumer, reference=replace(reference, consumer_version="A" * 64)),
            SourceHealthResolution(targets=(current,)),
        )
    with pytest.raises(ValueError):
        classify_source_health(
            consumer,
            SourceHealthResolution(
                targets=(replace(current, target_version="not-a-fingerprint"),)
            ),
        )


def test_character_fingerprint_overlay_is_one_state_query_one_import_and_no_cache_mutation(app):
    with app.app_context():
        repository = app.extensions["character_repository"]
        record = repository.get_character(TEST_CAMPAIGN_SLUG, "arden-march")
        assert record is not None
        page = repository.list_source_health_consumers(TEST_CAMPAIGN_SLUG)
        target = next(
            target
            for target in page.targets
            if target.canonical_identity
            == f"character:{TEST_CAMPAIGN_SLUG}:arden-march"
        )
        resolver = app.extensions["campaign_combat_preset_source_resolver"]
        version = resolver.build_character_source_version(record)
        reference = SourceHealthReference(
            target_kind="character",
            target_id="arden-march",
            consumer_version=version,
            version_scheme="combat-seed-v1-sha256",
        )
        cache_before = dict(repository._character_payload_cache)
        reset_db_query_metrics()

        batch = repository.overlay_source_health_character_fingerprints(
            TEST_CAMPAIGN_SLUG,
            (reference,),
            {reference: SourceHealthResolution(targets=(target,))},
            page.character_definitions,
            page.definition_bytes,
            target_version_adapter=resolver.build_character_source_version,
        )
        metrics = get_db_query_metrics()

        assert metrics["query_count"] == 2
        assert metrics["write_count"] == 0
        assert metrics["commit_count"] == 0
        assert batch.definition_file_count == 0
        assert batch.import_file_count == 1
        assert 0 < batch.import_bytes <= 524_288
        assert batch.definition_bytes + batch.import_bytes <= 8_388_608
        assert batch.resolutions[reference].targets[0].target_version == version
        assert repository._character_payload_cache.keys() == cache_before.keys()
        assert all(
            repository._character_payload_cache[key] is cached
            for key, cached in cache_before.items()
        )
def test_service_overlays_current_fingerprint_after_ordinary_resolution():
    consumer = SourceHealthConsumer(
        consumer_type="encounter-preset-entry",
        consumer_key="opaque",
        surface="Encounter preset",
        reference=SourceHealthReference(
            target_kind="dm_statblock",
            target_id="42",
            consumer_version="a" * 64,
            version_scheme="combat-seed-v1-sha256",
        ),
        accepted_target_types=("dm_statblock",),
    )
    ordinary_target = SourceHealthTarget(
        target_kind="dm_statblock",
        canonical_identity="dm_statblock:linden-pass:42",
        target_type="dm_statblock",
        destination="/campaigns/linden-pass/dm-content?lane=statblocks",
    )
    events: list[str] = []

    def resolve(_context, references):
        events.append("ordinary")
        return {
            reference: SourceHealthResolution(targets=(ordinary_target,))
            for reference in references
        }

    def overlay(_context, references, resolutions):
        events.append("fingerprint")
        assert resolutions[references[0]].targets == (ordinary_target,)
        return {
            **resolutions,
            references[0]: SourceHealthResolution(
                targets=(
                    replace(
                        ordinary_target,
                        target_version="b" * 64,
                        version_scheme="combat-seed-v1-sha256",
                    ),
                )
            ),
        }

    service = _service(
        authorize=lambda slug: SourceHealthAccessContext(
            campaign_slug=slug,
            system_code="DND-5E",
            library_slug="DND-5E",
        ),
        inventory_adapters=((
            "presets",
            lambda _context, _cursor: SourceHealthInventoryPage(
                consumers=(consumer,)
            ),
        ),),
        resolver=resolve,
        fingerprint_resolver=overlay,
    )

    report = service.build_report("linden-pass")

    assert events == ["ordinary", "fingerprint"]
    assert report.state == "findings"
    assert report.findings[0].classification == "stale-version"


def _target(**overrides) -> SourceHealthTarget:
    values = {
        "target_kind": "systems",
        "canonical_identity": "DND-5E:spell|PHB|shield",
        "system_code": "DND-5E",
        "target_type": "spell",
        "source_id": "PHB",
        "enabled": True,
        "accessible": True,
        "review_blocked": False,
        "target_version": "",
        "version_scheme": "",
        "destination": "/campaigns/linden-pass/systems/entries/phb-shield",
    }
    values.update(overrides)
    return SourceHealthTarget(**values)


def test_kernel_shapes_are_immutable_and_vocabularies_are_exact():
    consumer = _consumer()
    with pytest.raises(FrozenInstanceError):
        consumer.surface = "mutated"

    assert SOURCE_HEALTH_CLASSIFICATIONS == (
        "ambiguous",
        "missing",
        "wrong-system",
        "unsupported-type",
        "disabled",
        "inaccessible",
        "review-blocked",
        "stale-version",
        "healthy",
    )
    assert SOURCE_HEALTH_SEVERITIES == ("healthy", "attention", "blocked")
    assert SOURCE_HEALTH_ACTIONS == (
        "none",
        "inspect_consumer",
        "inspect_source",
        "manage_source_policy",
        "review_source",
        "contact_app_admin",
    )


@pytest.mark.parametrize(
    ("resolution", "expected"),
    [
        (SourceHealthResolution(ambiguous=True), "ambiguous"),
        (SourceHealthResolution(), "missing"),
        (SourceHealthResolution(targets=(_target(wrong_system=True),)), "wrong-system"),
        (SourceHealthResolution(targets=(_target(target_type="item"),)), "unsupported-type"),
        (SourceHealthResolution(targets=(_target(enabled=False),)), "disabled"),
        (SourceHealthResolution(targets=(_target(accessible=False),)), "inaccessible"),
        (SourceHealthResolution(targets=(_target(review_blocked=True),)), "review-blocked"),
        (
            SourceHealthResolution(
                targets=(
                    _target(
                        target_version="2",
                        version_scheme="integer",
                    ),
                )
            ),
            "stale-version",
        ),
        (SourceHealthResolution(targets=(_target(),)), "healthy"),
    ],
)
def test_first_match_precedence_matrix(resolution, expected):
    consumer = _consumer()
    if expected == "stale-version":
        consumer = replace(
            consumer,
            reference=_reference(consumer_version="1", version_scheme="integer"),
        )
    finding = classify_source_health(consumer, resolution)
    assert finding.classification == expected
    assert finding.severity == (
        "healthy" if expected == "healthy" else "attention" if expected == "stale-version" else "blocked"
    )


def test_ambiguous_precedes_all_target_failures_and_stale_needs_comparable_versions():
    consumer = replace(
        _consumer(),
        reference=_reference(consumer_version="old", version_scheme="opaque"),
    )
    target = _target(
        wrong_system=True,
        target_type="item",
        enabled=False,
        accessible=False,
        review_blocked=True,
        target_version="new",
        version_scheme="opaque",
    )
    assert classify_source_health(
        consumer,
        SourceHealthResolution(targets=(target,), ambiguous=True),
    ).classification == "ambiguous"
    assert classify_source_health(
        replace(consumer, accepted_target_types=("item",)),
        SourceHealthResolution(
            targets=(
                _target(
                    target_type="item",
                    target_version="new",
                    version_scheme="opaque",
                ),
            )
        ),
    ).classification == "healthy"


def test_inaccessible_target_is_redacted_and_has_no_destination_or_target_count():
    finding = classify_source_health(
        _consumer(),
        SourceHealthResolution(targets=(_target(accessible=False),)),
    )
    assert finding.classification == "inaccessible"
    assert finding.target is None
    assert finding.action == "none"

    payload = finding.to_payload()
    assert payload["target"] is None
    assert "target_count" not in payload
    assert "PHB" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("resolution", "expected_classification"),
    [
        (
            SourceHealthResolution(
                targets=(
                    _target(canonical_identity="DND-5E:PRIVATE:duplicate"),
                    _target(
                        canonical_identity="DND-5E:PRIVATE:duplicate",
                        accessible=False,
                    ),
                ),
            ),
            "inaccessible",
        ),
        (
            SourceHealthResolution(
                targets=(_target(canonical_identity="DND-5E:PRIVATE:aggregate"),),
                contains_inaccessible=True,
                policy_destination="/campaigns/linden-pass/private-policy",
            ),
            "inaccessible",
        ),
        (
            SourceHealthResolution(
                targets=(
                    _target(
                        canonical_identity="DND-5E:PRIVATE:precedence",
                        wrong_system=True,
                    ),
                    _target(
                        canonical_identity="DND-5E:PRIVATE:precedence",
                        accessible=False,
                    ),
                ),
                policy_destination="/campaigns/linden-pass/private-policy",
            ),
            "wrong-system",
        ),
    ],
)
def test_raw_inaccessible_participation_precedes_dedupe_and_redacts_every_hint(
    resolution,
    expected_classification,
):
    finding = classify_source_health(_consumer(), resolution)

    assert finding.classification == expected_classification
    assert finding.severity == "blocked"
    assert finding.target is None
    assert finding.action == "none"
    assert finding.destination == ""
    payload_text = json.dumps(finding.to_payload(), sort_keys=True)
    assert "PRIVATE" not in payload_text
    assert "PHB" not in payload_text
    assert "private-policy" not in payload_text
    assert "target_count" not in payload_text
    assert "contains_inaccessible" not in payload_text
    assert '"identity"' not in payload_text
    assert '"source_id"' not in payload_text


@pytest.mark.parametrize(
    "resolution",
    [
        SourceHealthResolution(targets=(_target(accessible=False, wrong_system=True),)),
        SourceHealthResolution(
            targets=(_target(accessible=False, target_type="item"),)
        ),
        SourceHealthResolution(
            targets=(_target(accessible=False, enabled=False),),
            policy_destination="/campaigns/linden-pass/dm-content?lane=systems",
        ),
        SourceHealthResolution(
            targets=(
                _target(canonical_identity="PRIVATE:one", accessible=False),
                _target(canonical_identity="PUBLIC:two", accessible=True),
            ),
            ambiguous=True,
            policy_destination="/campaigns/linden-pass/dm-content?lane=systems",
        ),
        SourceHealthResolution(
            ambiguous=True,
            policy_destination="/campaigns/linden-pass/dm-content?lane=systems",
            contains_inaccessible=True,
        ),
    ],
)
def test_any_inaccessible_participating_target_suppresses_all_navigation_and_metadata(
    resolution,
):
    finding = classify_source_health(_consumer(), resolution)

    assert finding.classification in {
        "ambiguous",
        "wrong-system",
        "unsupported-type",
        "disabled",
    }
    assert finding.target is None
    assert finding.action == "none"
    assert finding.destination == ""
    payload_text = json.dumps(finding.to_payload(), sort_keys=True)
    assert "PRIVATE" not in payload_text
    assert "PUBLIC" not in payload_text
    assert "dm-content" not in payload_text
    assert "target_count" not in payload_text


def test_authorization_precedes_inventory_and_view_as_context_is_owner_supplied():
    calls: list[str] = []

    def deny(campaign_slug: str):
        calls.append(f"authorize:{campaign_slug}")
        return None

    service = _service(
        authorize=deny,
        inventory_adapters=(
            ("inventory", lambda context, continuation: pytest.fail("inventory ran")),
        ),
        resolver=lambda context, references: pytest.fail("resolver ran"),
    )
    with pytest.raises(SourceHealthDenied):
        service.build_report("linden-pass")
    assert calls == ["authorize:linden-pass"]


def test_service_accepts_4096_unique_references_dedupes_and_preserves_bounds():
    context = SourceHealthAccessContext(
        campaign_slug="linden-pass",
        system_code="DND-5E",
        library_slug="DND-5E",
        can_view_private=False,
    )
    references = tuple(
        _reference(entry_key=f"spell|PHB|boundary-{index:04d}", slug="")
        for index in range(SOURCE_HEALTH_TARGET_REFERENCE_LIMIT)
    )
    consumers = tuple(
        _consumer(
            consumer_key=f"boundary-{index:04d}",
            reference=reference,
        )
        for index, reference in enumerate(references)
    ) + (
        _consumer(
            consumer_key="boundary-duplicate",
            reference=references[0],
        ),
    )
    resolver_calls: list[tuple[SourceHealthReference, ...]] = []

    def resolve(_context, pending_references):
        resolver_calls.append(tuple(pending_references))
        return {}

    service = SourceHealthService(
        authorize=lambda _slug: context,
        inventory_adapters=((
            "inventory",
            lambda _context, continuation: (
                pytest.fail(f"unexpected continuation: {continuation!r}")
                if continuation
                else SourceHealthInventoryPage(consumers=consumers)
            ),
        ),),
        resolver=resolve,
        character_resolver=lambda _context, pending_references: (
            pytest.fail(f"unexpected Character refs: {pending_references!r}")
        ),
        cursor_codec=SourceHealthBrowserCursorCodec(
            b"source-health-boundary-test-key-material"
        ),
    )

    report = service.build_report("linden-pass")

    assert resolver_calls == [references]
    assert len(resolver_calls[0]) == SOURCE_HEALTH_TARGET_REFERENCE_LIMIT == 4_096
    assert report.state == "partial"
    assert report.complete is False
    assert len(report.findings) == 50
    assert len(report.continuations) == 1
    assert report.continuations[0].startswith("sh2.")
    assert (
        len(report.continuations[0].encode("ascii"))
        <= SOURCE_HEALTH_BROWSER_CURSOR_MAX_BYTES
        == 3_840
    )
    assert len(serialize_source_health_report(report)) <= SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES


def test_service_rejects_4097_unique_references_before_every_resolver():
    context = SourceHealthAccessContext(
        campaign_slug="linden-pass",
        system_code="DND-5E",
        library_slug="DND-5E",
        can_view_private=False,
    )
    calls: list[str] = []
    consumers = tuple(
        _consumer(
            consumer_key=f"over-cap-{index:04d}",
            reference=_reference(
                entry_key=f"spell|PRIVATE|over-cap-{index:04d}",
                slug="",
            ),
        )
        for index in range(SOURCE_HEALTH_TARGET_REFERENCE_LIMIT + 1)
    )

    def forbidden(name):
        def fail(*_args):
            calls.append(name)
            pytest.fail(f"{name} resolver ran")

        return fail

    def authorize(_slug):
        calls.append("authorize")
        return context

    def inventory(_context, continuation):
        calls.append("inventory")
        assert continuation == ""
        return SourceHealthInventoryPage(consumers=consumers)

    service = SourceHealthService(
        authorize=authorize,
        inventory_adapters=(("inventory", inventory),),
        resolver=forbidden("ordinary"),
        character_resolver=forbidden("character"),
        character_fingerprint_resolver=forbidden("character-fingerprint"),
        fingerprint_resolver=forbidden("fingerprint"),
        cursor_codec=_cursor_codec(),
    )

    report = service.build_report("linden-pass")
    payload = serialize_source_health_report(report)

    assert calls == ["authorize", "inventory"]
    assert report.state == "error"
    assert report.complete is False
    assert report.findings == ()
    assert report.continuations == ()
    assert report.message == "Source Health could not complete. Refresh to retry."
    assert b"PRIVATE" not in payload
    assert b"4096" not in payload
    assert b"4097" not in payload
    assert b"cap" not in payload.lower()
    assert len(payload) <= SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES == 65_536


def test_service_uses_one_composite_cursor_without_exhausted_replay_or_false_final_state():
    context = SourceHealthAccessContext(
        campaign_slug="linden-pass",
        system_code="DND-5E",
        library_slug="DND-5E",
        can_view_private=False,
    )
    first_consumers = tuple(
        _consumer(
            consumer_key=f"character-{index:02d}",
            reference=_reference(entry_key=f"spell|PHB|{index:02d}", slug=""),
        )
        for index in range(55, -1, -1)
    )
    calls: list[tuple[str, str]] = []

    def characters(_context, continuation):
        calls.append(("characters", continuation))
        if continuation == "character:next":
            return SourceHealthInventoryPage(
                consumers=(
                    _consumer(
                        consumer_key="character-final",
                        reference=_reference(entry_key="spell|PHB|final", slug=""),
                    ),
                )
            )
        assert continuation == ""
        return SourceHealthInventoryPage(
            consumers=first_consumers,
            continuation="character:next",
            definition_file_count=50,
            definition_bytes=12345,
        )

    def mechanics(_context, continuation):
        calls.append(("mechanics", continuation))
        assert continuation == ""
        return SourceHealthInventoryPage(
            consumers=(
                _consumer(
                    consumer_type="mechanics",
                    consumer_key="mechanics-only",
                    reference=_reference(entry_key="spell|PHB|mechanics", slug=""),
                ),
            )
        )

    codec = _cursor_codec()
    service = SourceHealthService(
        cursor_codec=codec,
        authorize=lambda campaign_slug: context,
        inventory_adapters=(
            ("characters", characters),
            ("mechanics", mechanics),
        ),
        resolver=lambda _context, references: {
            reference: (
                SourceHealthResolution()
                if reference.entry_key == "spell|PHB|00"
                else SourceHealthResolution(
                    targets=(_target(canonical_identity=reference.entry_key),)
                )
            )
            for reference in references
        },
        character_resolver=lambda _context, references: SourceHealthResolutionBatch(
            resolutions={
                reference: SourceHealthResolution() for reference in references
            }
        ),
    )
    first = service.build_report("linden-pass")

    assert first.state == "partial"
    assert first.complete is False
    assert len(first.findings) == 50
    assert len(first.continuations) == 1
    first_state = codec.decode(first.continuations[0])
    assert first_state["version"] == 1
    assert first_state["campaign"] == "linden-pass"
    assert first_state["roster"] == ["characters", "mechanics"]
    assert first_state["window"]["count"] == 57
    assert first_state["window"]["offset"] == 50
    assert first_state["outcome"] == {
        "saw_any_consumer": True,
        "saw_nonhealthy": True,
    }

    second = service.build_report("linden-pass", continuation=first.continuations[0])
    assert second.state == "partial"
    assert len(second.findings) == 7
    assert len(second.continuations) == 1
    assert len({row.consumer.consumer_key for row in (*first.findings, *second.findings)}) == 57

    final = service.build_report("linden-pass", continuation=second.continuations[0])
    assert final.state == "findings"
    assert final.complete is True
    assert [row.consumer.consumer_key for row in final.findings] == ["character-final"]
    assert final.continuations == ()
    assert calls == [
        ("characters", ""),
        ("mechanics", ""),
        ("characters", ""),
        ("mechanics", ""),
        ("characters", "character:next"),
    ]
    assert first.measurements.definition_file_count == 50
    assert first.measurements.definition_bytes == 12345


def test_composite_cursor_rejects_tamper_context_roster_schema_and_offsets_before_inventory():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    calls: list[str] = []
    consumers = tuple(
        _consumer(
            consumer_key=f"cursor-{index:02d}",
            reference=_reference(entry_key=f"spell|PHB|cursor-{index:02d}", slug=""),
        )
        for index in range(51)
    )

    def inventory(_context, continuation):
        calls.append(continuation)
        return SourceHealthInventoryPage(consumers=consumers)

    codec = _cursor_codec()
    service = SourceHealthService(
        cursor_codec=codec,
        authorize=lambda _slug: context,
        inventory_adapters=(("character", inventory),),
        resolver=lambda _context, references: {
            reference: SourceHealthResolution(targets=(_target(),))
            for reference in references
        },
        character_resolver=lambda _context, references: SourceHealthResolutionBatch(
            resolutions={
                reference: SourceHealthResolution() for reference in references
            }
        ),
    )
    first = service.build_report("linden-pass")
    assert first.state == "partial"
    token = first.continuations[0]
    valid_state = codec.decode(token)
    assert codec.encode(valid_state) == token
    assert "cursor-00" not in token
    assert "spell|PHB|cursor-00" not in token
    inventory_call_count = len(calls)

    prefix, body_segment, signature_segment = token.split(".")
    assert len(body_segment) % 4 in {2, 3}
    assert len(signature_segment) % 4 in {2, 3}
    invalid_tokens = [
        "report:50",
        token[:-1] + ("A" if token[-1] != "A" else "B"),
        f"{prefix}.{body_segment + ('=' * (-len(body_segment) % 4))}.{signature_segment}",
        f"{prefix}.{body_segment}.{signature_segment + ('=' * (-len(signature_segment) % 4))}",
        f"{prefix}.{_equivalent_noncanonical_b64_segment(body_segment)}.{signature_segment}",
        f"{prefix}.{body_segment}.{_equivalent_noncanonical_b64_segment(signature_segment)}",
    ]
    for mutate in (
        lambda state: state.update(campaign="other-campaign"),
        lambda state: state.update(roster=["renamed-adapter"]),
        lambda state: state.update(unexpected=True),
        lambda state: state["window"].update(offset=-50),
        lambda state: state["window"].update(offset=25),
        lambda state: state["window"].update(count=50),
    ):
        state = json.loads(json.dumps(valid_state))
        mutate(state)
        invalid_tokens.append(codec.encode(state))

    for invalid_token in invalid_tokens:
        report = service.build_report("linden-pass", continuation=invalid_token)
        assert report.state == "error"
        assert report.complete is False
        assert report.findings == ()
        assert report.continuations == ()
        assert report.message == "Source Health could not complete. Refresh to retry."
        assert len(calls) == inventory_call_count


def test_composite_cursor_binds_the_recomputed_finding_window():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    mutable_count = [51]

    def inventory(_context, _continuation):
        return SourceHealthInventoryPage(
            consumers=tuple(
                _consumer(
                    consumer_key=f"bound-{index:02d}",
                    reference=_reference(entry_key=f"spell|PHB|bound-{index:02d}", slug=""),
                )
                for index in range(mutable_count[0])
            )
        )

    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=(("characters", inventory),),
        resolver=lambda _context, references: {
            reference: SourceHealthResolution(targets=(_target(),))
            for reference in references
        },
    )
    first = service.build_report("linden-pass")
    mutable_count[0] = 50

    stale_window = service.build_report(
        "linden-pass",
        continuation=first.continuations[0],
    )

    assert stale_window.state == "error"
    assert stale_window.complete is False
    assert stale_window.findings == ()
    assert stale_window.continuations == ()


def test_character_references_are_held_until_read_budget_is_available_without_duplicates():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    calls: list[tuple[str, str]] = []
    held_found = SourceHealthConsumer(
        consumer_type="combatant",
        consumer_key="combatant:found",
        surface="Combat",
        reference=SourceHealthReference("character", target_id="target-z"),
        accepted_target_types=("character",),
        destination="/campaigns/linden-pass/combat/dm?combatant=found",
    )
    held_missing = replace(
        held_found,
        consumer_key="combatant:missing",
        reference=SourceHealthReference("character", target_id="target-missing"),
    )

    def characters(_context, continuation):
        calls.append(("characters", continuation))
        if continuation == "character:page-2":
            return SourceHealthInventoryPage(
                targets=(
                    SourceHealthTarget(
                        target_kind="character",
                        canonical_identity="character:linden-pass:target-z",
                        target_type="character",
                    ),
                ),
                continuation="character:page-3",
            )
        if continuation == "character:page-3":
            return SourceHealthInventoryPage()
        assert continuation == ""
        return SourceHealthInventoryPage(
            targets=(
                SourceHealthTarget(
                    target_kind="character",
                    canonical_identity="character:linden-pass:target-a",
                    target_type="character",
                ),
            ),
            continuation="character:page-2",
            definition_file_count=50,
        )

    def combat(_context, continuation):
        calls.append(("combat", continuation))
        assert continuation == ""
        return SourceHealthInventoryPage(consumers=(held_found, held_missing))

    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=(("characters", characters), ("combat", combat)),
        resolver=lambda *_: {},
    )

    first = service.build_report("linden-pass")
    assert first.state == "partial"
    assert first.findings == ()
    assert "target-z" not in first.continuations[0]
    assert "target-missing" not in first.continuations[0]

    second = service.build_report("linden-pass", continuation=first.continuations[0])
    assert second.state == "partial"
    assert [(row.consumer.consumer_key, row.classification) for row in second.findings] == [
        ("combatant:missing", "missing"),
        ("combatant:found", "healthy"),
    ]

    final = service.build_report("linden-pass", continuation=second.continuations[0])
    assert final.state == "findings"
    assert final.findings == ()
    assert calls == [
        ("characters", ""),
        ("combat", ""),
        ("characters", "character:page-2"),
        ("combat", ""),
        ("characters", "character:page-3"),
    ]


def test_exact_character_resolver_handles_a_late_combat_reference_after_inventory_exhaustion():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    hero_reference = SourceHealthReference("character", target_id="hero")
    hero_consumer = SourceHealthConsumer(
        consumer_type="combatant",
        consumer_key="combatant:hero",
        surface="Combat",
        reference=hero_reference,
        accepted_target_types=("character",),
        destination="/campaigns/linden-pass/combat/dm?combatant=hero",
    )
    combat_calls: list[str] = []
    exact_calls: list[tuple[SourceHealthReference, ...]] = []

    def combat(_context, continuation):
        combat_calls.append(continuation)
        if continuation == "combat:late":
            return SourceHealthInventoryPage(consumers=(hero_consumer,))
        assert continuation == ""
        return SourceHealthInventoryPage(continuation="combat:late")

    def exact(_context, references):
        exact_calls.append(references)
        return SourceHealthResolutionBatch(
            resolutions={
                hero_reference: SourceHealthResolution(
                    targets=(
                        SourceHealthTarget(
                            target_kind="character",
                            canonical_identity="character:linden-pass:hero",
                            system_code="DND-5E",
                            target_type="character",
                            destination="/campaigns/linden-pass/characters/hero",
                        ),
                    )
                )
            },
            definition_file_count=1,
            definition_bytes=321,
        )

    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=(
            ("characters", lambda *_: SourceHealthInventoryPage()),
            ("combat", combat),
        ),
        resolver=lambda _context, references: (
            pytest.fail(f"general resolver received Character refs: {references!r}")
            if references
            else {}
        ),
        character_resolver=exact,
    )

    first = service.build_report("linden-pass")
    assert first.state == "partial"
    assert first.findings == ()
    assert "hero" not in first.continuations[0]

    final = service.build_report("linden-pass", continuation=first.continuations[0])
    assert final.state == "healthy"
    assert final.complete is True
    assert [(row.consumer.consumer_key, row.classification) for row in final.findings] == [
        ("combatant:hero", "healthy")
    ]
    assert final.measurements.definition_file_count == 1
    assert final.measurements.definition_bytes == 321
    assert exact_calls == [(hero_reference,)]
    assert combat_calls == ["", "combat:late"]


def test_character_exact_resolution_uses_inventory_overlap_dedupes_and_shares_read_budget():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    overlap_reference = SourceHealthReference("character", target_id="hero")
    villain_by_id = SourceHealthReference("character", target_id="villain")
    villain_by_slug = SourceHealthReference("character", slug="villain")
    consumers = tuple(
        SourceHealthConsumer(
            consumer_type="combatant",
            consumer_key=f"combatant:{index}",
            surface="Combat",
            reference=reference,
            accepted_target_types=("character",),
        )
        for index, reference in enumerate(
            (overlap_reference, villain_by_id, villain_by_slug)
        )
    )
    exact_calls: list[tuple[SourceHealthReference, ...]] = []

    def exact(_context, references):
        exact_calls.append(references)
        assert len(references) == 1
        assert references[0] in {villain_by_id, villain_by_slug}
        return SourceHealthResolutionBatch(
            resolutions={
                references[0]: SourceHealthResolution(
                    targets=(
                        SourceHealthTarget(
                            target_kind="character",
                            canonical_identity="character:linden-pass:villain",
                            system_code="DND-5E",
                            target_type="character",
                        ),
                    )
                )
            },
            definition_file_count=1,
            definition_bytes=123,
        )

    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=(
            (
                "characters",
                lambda *_: SourceHealthInventoryPage(
                    targets=(
                        SourceHealthTarget(
                            target_kind="character",
                            canonical_identity="character:linden-pass:hero",
                            system_code="DND-5E",
                            target_type="character",
                        ),
                    ),
                    definition_file_count=49,
                    definition_bytes=4_900,
                ),
            ),
            ("combat", lambda *_: SourceHealthInventoryPage(consumers=consumers)),
        ),
        resolver=lambda _context, references: (
            pytest.fail(f"general resolver received Character refs: {references!r}")
            if references
            else {}
        ),
        character_resolver=exact,
    )

    report = service.build_report("linden-pass")
    assert report.state == "healthy"
    assert [finding.classification for finding in report.findings] == [
        "healthy",
        "healthy",
        "healthy",
    ]
    assert report.measurements.definition_file_count == 50
    assert report.measurements.definition_bytes == 5_023
    assert exact_calls and len(exact_calls[0]) == 1


def test_character_exact_resolution_holds_when_inventory_consumes_the_read_budget():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    hero_reference = SourceHealthReference("character", target_id="budget-hero")
    hero_consumer = SourceHealthConsumer(
        consumer_type="combatant",
        consumer_key="combatant:budget-hero",
        surface="Combat",
        reference=hero_reference,
        accepted_target_types=("character",),
    )
    character_calls: list[str] = []
    exact_calls: list[tuple[SourceHealthReference, ...]] = []

    def characters(_context, continuation):
        character_calls.append(continuation)
        if continuation == "characters:done":
            return SourceHealthInventoryPage()
        assert continuation == ""
        return SourceHealthInventoryPage(
            continuation="characters:done",
            definition_file_count=50,
            definition_bytes=5_000,
        )

    def exact(_context, references):
        exact_calls.append(references)
        return SourceHealthResolutionBatch(
            resolutions={
                hero_reference: SourceHealthResolution(
                    targets=(
                        SourceHealthTarget(
                            target_kind="character",
                            canonical_identity="character:linden-pass:budget-hero",
                            target_type="character",
                        ),
                    )
                )
            },
            definition_file_count=1,
            definition_bytes=100,
        )

    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=(
            ("characters", characters),
            (
                "combat",
                lambda _context, continuation: (
                    SourceHealthInventoryPage(consumers=(hero_consumer,))
                    if continuation == ""
                    else pytest.fail("held Combat owner cursor advanced")
                ),
            ),
        ),
        resolver=lambda *_: {},
        character_resolver=exact,
    )

    first = service.build_report("linden-pass")
    assert first.state == "partial"
    assert first.findings == ()
    assert first.measurements.definition_file_count == 50
    assert "budget-hero" not in first.continuations[0]
    assert exact_calls == []

    final = service.build_report("linden-pass", continuation=first.continuations[0])
    assert final.state == "healthy"
    assert [(finding.consumer.consumer_key, finding.classification) for finding in final.findings] == [
        ("combatant:budget-hero", "healthy")
    ]
    assert final.measurements.definition_file_count == 1
    assert exact_calls == [(hero_reference,)]
    assert character_calls == ["", "characters:done"]


@pytest.mark.parametrize("owner_count,reference_count", [(2, 1), (1, 51)])
def test_character_exact_resolution_allows_bounded_multiple_owners_but_rejects_over_fifty_refs(
    owner_count, reference_count
):
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)
    exact_calls: list[tuple[SourceHealthReference, ...]] = []
    registrations: list[tuple[str, object]] = [
        ("characters", lambda *_: SourceHealthInventoryPage())
    ]
    for owner_index in range(owner_count):
        registrations.append(
            (
                f"owner-{owner_index}",
                lambda *_args, owner_index=owner_index: SourceHealthInventoryPage(
                    consumers=tuple(
                        SourceHealthConsumer(
                            consumer_type="combatant",
                            consumer_key=f"owner-{owner_index}:{index}",
                            surface="Combat",
                            reference=SourceHealthReference(
                                "character",
                                target_id=f"target-{owner_index}-{index}",
                            ),
                        )
                        for index in range(reference_count)
                    )
                ),
            )
        )

    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=tuple(registrations),
        resolver=lambda *_: {},
        character_resolver=lambda _context, references: (
            exact_calls.append(references)
            or SourceHealthResolutionBatch(
                resolutions={
                    reference: SourceHealthResolution() for reference in references
                }
            )
        ),
    )
    report = service.build_report("linden-pass")
    if owner_count == 2:
        assert report.state == "findings"
        assert len(report.findings) == 2
        assert len(exact_calls) == 1 and len(exact_calls[0]) == 2
    else:
        assert report.state == "error"
        assert report.findings == ()
        assert exact_calls == []


def test_service_healthy_empty_error_and_stale_states_are_sanitized_private_no_store():
    context = SourceHealthAccessContext("linden-pass", "DND-5E", "DND-5E", False)

    empty_service = _service(
        authorize=lambda slug: context,
        inventory_adapters=(("inventory", lambda *_: SourceHealthInventoryPage()),),
        resolver=lambda *_: {},
    )
    empty = empty_service.build_report("linden-pass")
    assert empty.state == "empty"

    healthy_service = _service(
        authorize=lambda slug: context,
        inventory_adapters=(
            ("inventory", lambda *_: SourceHealthInventoryPage(consumers=(_consumer(),))),
        ),
        resolver=lambda _context, references: {
            reference: SourceHealthResolution(targets=(_target(),)) for reference in references
        },
    )
    healthy = healthy_service.build_report("linden-pass")
    assert healthy.state == "healthy"
    payload_bytes = serialize_source_health_report(healthy)
    assert len(payload_bytes) < 65_536
    payload = json.loads(payload_bytes)
    assert payload["payload_policy"] == {
        "cache_control": "private, no-store",
        "contains_private_data": True,
    }

    error_service = _service(
        authorize=lambda slug: context,
        inventory_adapters=(
            (
                "inventory",
                lambda *_: (_ for _ in ()).throw(RuntimeError("PRIVATE PATH C:/secret")),
            ),
        ),
        resolver=lambda *_: {},
    )
    error = error_service.build_report("linden-pass")
    assert error.state == "error"
    assert error.findings == ()
    assert "secret" not in error.message.lower()
    assert mark_source_health_report_stale(healthy).state == "report_stale"


def test_mechanics_inventory_reads_published_metadata_only_and_nested_refs(app):
    with app.app_context():
        store = CampaignPageStore()
        store.upsert_page(
            TEST_CAMPAIGN_SLUG,
            "mechanics/source-health",
            metadata={
                "title": "Source Health",
                "section": "Mechanics",
                "page_type": "mechanic",
                "published": True,
                "character_option": {
                    "base_rule_refs": [{"entry_key": "rule|direct", "entry_type": "rule"}],
                },
                "character_progression": {
                    "character_option": {
                        "base_rule_refs": [
                            {
                                "rule_key": "Armor Class",
                                "source_version": "1",
                                "version_scheme": "integer",
                            }
                        ],
                    }
                },
            },
            body_markdown="PRIVATE BODY MUST NOT LOAD",
        )
        store.upsert_page(
            TEST_CAMPAIGN_SLUG,
            "mechanics/unpublished",
            metadata={
                "title": "Unpublished",
                "section": "Mechanics",
                "page_type": "mechanic",
                "published": False,
                "character_option": {"base_rule_refs": [{"entry_key": "rule|hidden"}]},
            },
            body_markdown="PRIVATE UNPUBLISHED BODY",
        )

        reset_db_query_metrics()
        page = store.list_source_health_mechanics_consumers(TEST_CAMPAIGN_SLUG)
        metrics = get_db_query_metrics()

    assert [consumer.reference.entry_key for consumer in page.consumers] == ["rule|direct", ""]
    assert page.consumers[1].reference.rule_key == "armor-class"
    assert page.consumers[1].reference.consumer_version == "1"
    assert page.consumers[1].reference.version_scheme == "integer"
    assert metrics["query_count"] == 1
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0


def _mechanics_health_metadata(page_ref: str) -> dict[str, object]:
    token = page_ref.rsplit("/", 1)[-1]
    return {
        "title": f"Health {token}",
        "route_slug": f"private-route-{token}",
        "section": "Mechanics",
        "page_type": "mechanic",
        "published": True,
        "character_option": {
            "base_rule_refs": [
                {
                    "entry_key": f"rule|private|{token}",
                    "entry_type": "rule",
                }
            ]
        },
    }


def _seed_mechanics_health_pages(
    store: CampaignPageStore,
    page_refs: list[str],
) -> None:
    for page_ref in page_refs:
        store.upsert_page(
            TEST_CAMPAIGN_SLUG,
            page_ref,
            metadata=_mechanics_health_metadata(page_ref),
            body_markdown=f"PRIVATE BODY {page_ref}",
        )


def _seed_combat_health_consumers(
    store: CampaignCombatStore,
    count: int,
) -> list[int]:
    return [
        store.create_combatant(
            TEST_CAMPAIGN_SLUG,
            combatant_type="npc",
            display_name=f"PRIVATE COMBATANT {index:03d}",
            source_kind="systems_monster",
            source_ref=f"monster|PRIVATE|{index:03d}",
        ).id
        for index in range(count)
    ]


def test_owner_cursor_grammar_is_strict_and_legacy_is_rejected_before_sql(app):
    digest = "a" * 64
    invalid_by_owner = (
        (
            CampaignPageStore().list_source_health_mechanics_consumers,
            (
                " ",
                f" mh1:1:{digest}",
                f"mh1:1:{digest} ",
                f"mh1:+1:{digest}",
                f"mh1:01:{digest}",
                f"mh1:0:{digest}",
                f"mh1:-1:{digest}",
                f"mh1:1.0:{digest}",
                f"mh1:1:{digest}:extra",
                f"mh1:1:{'A' * 64}",
                f"mh1:1:{'a' * 63}",
                f"mh1:9223372036854775808:{digest}",
                "mechanics:private-page-ref",
                f"ch1:1:{digest}",
            ),
        ),
        (
            CampaignCombatStore().list_source_health_consumers,
            (
                " ",
                f" ch1:1:{digest}",
                f"ch1:1:{digest} ",
                f"ch1:+1:{digest}",
                f"ch1:01:{digest}",
                f"ch1:0:{digest}",
                f"ch1:-1:{digest}",
                f"ch1:1.0:{digest}",
                f"ch1:1:{digest}:extra",
                f"ch1:1:{'A' * 64}",
                f"ch1:1:{'a' * 63}",
                f"ch1:9223372036854775808:{digest}",
                "combat:12345",
                f"mh1:1:{digest}",
            ),
        ),
    )

    with app.app_context():
        for owner_adapter, invalid_cursors in invalid_by_owner:
            for invalid_cursor in invalid_cursors:
                reset_db_query_metrics()
                with pytest.raises(SourceHealthCursorError):
                    owner_adapter(
                        TEST_CAMPAIGN_SLUG,
                        continuation=invalid_cursor,
                    )
                assert get_db_query_metrics()["query_count"] == 0


def test_mechanics_owner_cursor_is_private_exact_once_and_bounded(app, monkeypatch):
    page_refs = [f"mechanics/private-{index:03d}" for index in range(53)]
    with app.app_context():
        store = CampaignPageStore()
        _seed_mechanics_health_pages(store, page_refs)
        recorder = _RecordingConnection(get_db())
        monkeypatch.setattr(campaign_page_store_module, "get_db", lambda: recorder)
        codec = _cursor_codec()
        context = SourceHealthAccessContext(
            TEST_CAMPAIGN_SLUG,
            "DND-5E",
            "DND-5E",
            False,
        )
        service = _service(
            authorize=lambda _slug: context,
            inventory_adapters=(
                (
                    "mechanics",
                    lambda _context, continuation: store.list_source_health_mechanics_consumers(
                        TEST_CAMPAIGN_SLUG,
                        continuation=continuation,
                    ),
                ),
            ),
            resolver=lambda _context, references: {
                reference: SourceHealthResolution() for reference in references
            },
            cursor_codec=codec,
        )

        first = service.build_report(TEST_CAMPAIGN_SLUG)
        decoded = codec.decode(first.continuations[0])
        owner_cursor = decoded["adapters"][0]["cursor"]
        second = service.build_report(
            TEST_CAMPAIGN_SLUG,
            continuation=first.continuations[0],
        )

    emitted_refs = [
        finding.consumer.consumer_key.split(":", 1)[0]
        for finding in (*first.findings, *second.findings)
    ]
    assert emitted_refs == page_refs
    assert len(set(emitted_refs)) == 53
    assert first.complete is False
    assert second.complete is True
    assert owner_cursor.startswith("mh1:50:")
    assert len(owner_cursor.split(":")) == 3
    assert len(owner_cursor.split(":")[2]) == 64
    decoded_text = json.dumps(decoded, sort_keys=True)
    assert all(page_ref not in decoded_text for page_ref in page_refs)
    assert "private-route" not in decoded_text
    assert "rule|private" not in decoded_text
    assert len(recorder.records) == 2
    assert recorder.records[0]["parameters"] == (TEST_CAMPAIGN_SLUG, 51, 0)
    assert recorder.records[0]["row_count"] == 51
    assert recorder.records[0]["row_keys"] == page_refs[:51]
    assert recorder.records[1]["parameters"] == (TEST_CAMPAIGN_SLUG, 52, 49)
    assert recorder.records[1]["row_count"] == 4
    assert recorder.records[1]["row_keys"] == page_refs[49:]
    assert all(
        "ORDER BY page_ref COLLATE BINARY ASC LIMIT ? OFFSET ?" in record["sql"]
        for record in recorder.records
    )


def test_combat_owner_cursor_is_private_exact_once_and_bounded(app, monkeypatch):
    with app.app_context():
        store = CampaignCombatStore()
        combatant_ids = _seed_combat_health_consumers(store, 53)
        recorder = _RecordingConnection(get_db())
        monkeypatch.setattr(campaign_combat_store_module, "get_db", lambda: recorder)
        codec = _cursor_codec()
        context = SourceHealthAccessContext(
            TEST_CAMPAIGN_SLUG,
            "DND-5E",
            "DND-5E",
            False,
        )
        service = _service(
            authorize=lambda _slug: context,
            inventory_adapters=(
                (
                    "combat",
                    lambda _context, continuation: store.list_source_health_consumers(
                        TEST_CAMPAIGN_SLUG,
                        continuation=continuation,
                    ),
                ),
            ),
            resolver=lambda _context, references: {
                reference: SourceHealthResolution() for reference in references
            },
            cursor_codec=codec,
        )

        first = service.build_report(TEST_CAMPAIGN_SLUG)
        decoded = codec.decode(first.continuations[0])
        owner_cursor = decoded["adapters"][0]["cursor"]
        second = service.build_report(
            TEST_CAMPAIGN_SLUG,
            continuation=first.continuations[0],
        )

    emitted_ids = [
        int(finding.consumer.consumer_key.partition(":")[2])
        for finding in (*first.findings, *second.findings)
    ]
    assert set(emitted_ids) == set(combatant_ids)
    assert len(set(emitted_ids)) == 53
    assert first.complete is False
    assert second.complete is True
    assert owner_cursor.startswith("ch1:50:")
    assert len(owner_cursor.split(":")) == 3
    assert len(owner_cursor.split(":")[2]) == 64
    decoded_text = json.dumps(decoded, sort_keys=True)
    assert "monster|PRIVATE" not in decoded_text
    assert "combatant=" not in decoded_text
    assert len(recorder.records) == 2
    assert recorder.records[0]["parameters"] == (TEST_CAMPAIGN_SLUG, 51, 0)
    assert recorder.records[0]["row_count"] == 51
    assert recorder.records[0]["row_keys"] == combatant_ids[:51]
    assert recorder.records[1]["parameters"] == (TEST_CAMPAIGN_SLUG, 52, 49)
    assert recorder.records[1]["row_count"] == 4
    assert recorder.records[1]["row_keys"] == combatant_ids[49:]
    assert all(
        "ORDER BY id ASC LIMIT ? OFFSET ?" in record["sql"]
        for record in recorder.records
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "insert_before",
        "delete_before",
        "delete_anchor",
        "anchor_key",
        "anchor_route",
        "anchor_metadata",
        "anchor_updated_at",
    ),
)
def test_mechanics_owner_cursor_rejects_before_or_anchor_drift(
    app,
    mutation,
):
    page_refs = [
        "mechanics/drift-10",
        "mechanics/drift-20",
        "mechanics/drift-30",
        "mechanics/drift-40",
    ]
    with app.app_context():
        store = CampaignPageStore()
        _seed_mechanics_health_pages(store, page_refs)
        first = store.list_source_health_mechanics_consumers(
            TEST_CAMPAIGN_SLUG,
            limit=2,
        )
        assert first.continuation
        connection = get_db()
        if mutation == "insert_before":
            _seed_mechanics_health_pages(store, ["mechanics/drift-05"])
        elif mutation == "delete_before":
            store.delete_page(TEST_CAMPAIGN_SLUG, page_refs[0])
        elif mutation == "delete_anchor":
            store.delete_page(TEST_CAMPAIGN_SLUG, page_refs[1])
        elif mutation == "anchor_key":
            connection.execute(
                """
                UPDATE campaign_pages
                SET page_ref = ?
                WHERE campaign_slug = ? AND page_ref = ?
                """,
                ("mechanics/drift-25", TEST_CAMPAIGN_SLUG, page_refs[1]),
            )
            connection.commit()
        elif mutation == "anchor_route":
            connection.execute(
                """
                UPDATE campaign_pages
                SET route_slug = ?
                WHERE campaign_slug = ? AND page_ref = ?
                """,
                ("private-route-drifted", TEST_CAMPAIGN_SLUG, page_refs[1]),
            )
            connection.commit()
        elif mutation == "anchor_metadata":
            connection.execute(
                """
                UPDATE campaign_pages
                SET metadata_json = ?
                WHERE campaign_slug = ? AND page_ref = ?
                """,
                (
                    json.dumps(
                        _mechanics_health_metadata(page_refs[1])
                        | {"summary": "PRIVATE DRIFT"},
                        sort_keys=True,
                    ),
                    TEST_CAMPAIGN_SLUG,
                    page_refs[1],
                ),
            )
            connection.commit()
        else:
            connection.execute(
                """
                UPDATE campaign_pages
                SET updated_at = ?
                WHERE campaign_slug = ? AND page_ref = ?
                """,
                ("2099-01-01T00:00:00Z", TEST_CAMPAIGN_SLUG, page_refs[1]),
            )
            connection.commit()

        reset_db_query_metrics()
        with pytest.raises(SourceHealthCursorError):
            store.list_source_health_mechanics_consumers(
                TEST_CAMPAIGN_SLUG,
                continuation=first.continuation,
                limit=2,
            )
        metrics = get_db_query_metrics()

    assert metrics["query_count"] == 1
    assert metrics["write_count"] == 0


def test_mechanics_owner_cursor_allows_after_anchor_changes_without_replay(app):
    page_refs = [f"mechanics/after-{index}" for index in (10, 20, 30, 40, 50)]
    with app.app_context():
        store = CampaignPageStore()
        _seed_mechanics_health_pages(store, page_refs)
        page = store.list_source_health_mechanics_consumers(
            TEST_CAMPAIGN_SLUG,
            limit=2,
        )
        emitted = [consumer.consumer_key.split(":", 1)[0] for consumer in page.consumers]
        store.delete_page(TEST_CAMPAIGN_SLUG, page_refs[2])
        added_ref = "mechanics/after-60"
        _seed_mechanics_health_pages(store, [added_ref])
        query_count = 1
        while page.continuation:
            page = store.list_source_health_mechanics_consumers(
                TEST_CAMPAIGN_SLUG,
                continuation=page.continuation,
                limit=2,
            )
            query_count += 1
            emitted.extend(
                consumer.consumer_key.split(":", 1)[0]
                for consumer in page.consumers
            )

    assert emitted == [page_refs[0], page_refs[1], page_refs[3], page_refs[4], added_ref]
    assert len(set(emitted)) == len(emitted)
    assert query_count == 3


@pytest.mark.parametrize(
    "mutation",
    (
        "insert_before",
        "delete_before",
        "delete_anchor",
        "anchor_key",
        "anchor_source_kind",
        "anchor_source_ref",
    ),
)
def test_combat_owner_cursor_rejects_before_or_anchor_drift(app, mutation):
    with app.app_context():
        store = CampaignCombatStore()
        combatant_ids = _seed_combat_health_consumers(store, 5)
        if mutation == "insert_before":
            store.delete_combatant(TEST_CAMPAIGN_SLUG, combatant_ids[1])
            expected_anchor = combatant_ids[2]
        else:
            expected_anchor = combatant_ids[1]
        first = store.list_source_health_consumers(
            TEST_CAMPAIGN_SLUG,
            limit=2,
        )
        assert first.continuation
        assert int(first.consumers[-1].consumer_key.partition(":")[2]) == expected_anchor
        connection = get_db()
        if mutation == "insert_before":
            inserted_id = _seed_combat_health_consumers(store, 1)[0]
            connection.execute(
                "UPDATE campaign_combatants SET id = ? WHERE id = ?",
                (combatant_ids[1], inserted_id),
            )
            connection.commit()
        elif mutation == "delete_before":
            store.delete_combatant(TEST_CAMPAIGN_SLUG, combatant_ids[0])
        elif mutation == "delete_anchor":
            store.delete_combatant(TEST_CAMPAIGN_SLUG, expected_anchor)
        elif mutation == "anchor_key":
            connection.execute(
                "UPDATE campaign_combatants SET id = ? WHERE id = ?",
                (max(combatant_ids) + 10, expected_anchor),
            )
            connection.commit()
        elif mutation == "anchor_source_kind":
            connection.execute(
                "UPDATE campaign_combatants SET source_kind = ? WHERE id = ?",
                ("character", expected_anchor),
            )
            connection.commit()
        else:
            connection.execute(
                "UPDATE campaign_combatants SET source_ref = ? WHERE id = ?",
                ("monster|PRIVATE|drifted", expected_anchor),
            )
            connection.commit()

        reset_db_query_metrics()
        with pytest.raises(SourceHealthCursorError):
            store.list_source_health_consumers(
                TEST_CAMPAIGN_SLUG,
                continuation=first.continuation,
                limit=2,
            )
        metrics = get_db_query_metrics()

    assert metrics["query_count"] == 1
    assert metrics["write_count"] == 0


def test_combat_owner_cursor_allows_after_anchor_changes_without_replay(app):
    with app.app_context():
        store = CampaignCombatStore()
        combatant_ids = _seed_combat_health_consumers(store, 5)
        page = store.list_source_health_consumers(TEST_CAMPAIGN_SLUG, limit=2)
        emitted = [
            int(consumer.consumer_key.partition(":")[2])
            for consumer in page.consumers
        ]
        store.delete_combatant(TEST_CAMPAIGN_SLUG, combatant_ids[2])
        added_id = _seed_combat_health_consumers(store, 1)[0]
        query_count = 1
        while page.continuation:
            page = store.list_source_health_consumers(
                TEST_CAMPAIGN_SLUG,
                continuation=page.continuation,
                limit=2,
            )
            query_count += 1
            emitted.extend(
                int(consumer.consumer_key.partition(":")[2])
                for consumer in page.consumers
            )

    assert emitted == [
        combatant_ids[0],
        combatant_ids[1],
        combatant_ids[3],
        combatant_ids[4],
        added_id,
    ]
    assert len(set(emitted)) == len(emitted)
    assert query_count == 3


def test_character_inventory_reads_owner_refs_for_dnd_and_xianxia_without_state_or_derivation(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    characters_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / TEST_CAMPAIGN_SLUG
        / "characters"
    )
    definitions = {
        "aa-health-dnd": {
            "campaign_slug": TEST_CAMPAIGN_SLUG,
            "character_slug": "aa-health-dnd",
            "status": "active",
            "system": "DND-5E",
            "profile": {
                "classes": [
                    {
                        "systems_ref": {"entry_key": "class|PHB|fighter"},
                        "subclass_ref": {"entry_key": "subclass|PHB|champion"},
                    }
                ],
                "species_ref": {"entry_key": "race|PHB|human"},
                "background_ref": {"entry_key": "background|PHB|soldier"},
                "species_page_ref": "mechanics/species-human",
                "background_page_ref": "mechanics/background-soldier",
            },
            "features": [
                {
                    "systems_ref": {"entry_key": "classfeature|PHB|second-wind"},
                    "page_ref": "mechanics/second-wind",
                }
            ],
            "spellcasting": {
                "spells": [
                    {
                        "systems_ref": {"entry_key": "spell|PHB|shield"},
                        "page_ref": "mechanics/shield",
                    }
                ]
            },
            "equipment_catalog": [
                {
                    "systems_ref": {"entry_key": "item|PHB|longsword"},
                    "page_ref": "mechanics/longsword",
                }
            ],
            "derived": {"systems_ref": {"entry_key": "must|not|scan"}},
        },
        "ab-health-xianxia": {
            "campaign_slug": TEST_CAMPAIGN_SLUG,
            "character_slug": "ab-health-xianxia",
            "status": "active",
            "system": "XIANXIA",
            "profile": {},
            "xianxia": {
                "martial_arts": [
                    {"systems_ref": {"entry_key": "martial_art|custom|cloud"}}
                ],
                "generic_techniques": [
                    {"systems_ref": {"entry_key": "technique|custom|step"}}
                ],
                "equipment": {
                    "necessary_weapons": [
                        {"systems_ref": {"entry_key": "item|custom|sword"}}
                    ],
                    "necessary_tools": [
                        {"systems_ref": {"entry_key": "item|custom|kit"}}
                    ],
                },
            },
        },
    }
    for character_slug, definition in definitions.items():
        character_dir = characters_dir / character_slug
        character_dir.mkdir(parents=True, exist_ok=True)
        (character_dir / "definition.yaml").write_text(
            yaml.safe_dump(definition, sort_keys=False),
            encoding="utf-8",
        )

    def forbidden(*_args, **_kwargs):
        pytest.fail("Source Health entered Character state, derivation, or full-load code")

    monkeypatch.setattr(repository, "_load_character", forbidden)
    monkeypatch.setattr(character_repository_module, "build_initial_state", forbidden)
    for method_name in (
        "prepare_initial_state",
        "insert_initial_state_in_transaction",
        "get_state",
        "initialize_state_if_missing",
        "replace_state",
    ):
        monkeypatch.setattr(repository.state_store, method_name, forbidden)

    original_read_bytes = Path.read_bytes
    reads: list[Path] = []

    def tracked_read_bytes(path: Path) -> bytes:
        reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    character_cache_before = dict(repository._character_payload_cache)
    config_cache_before = dict(repository._campaign_config_cache)

    reset_db_query_metrics()
    page = repository.list_source_health_consumers(TEST_CAMPAIGN_SLUG, limit=2)
    metrics = get_db_query_metrics()

    consumer_keys = {consumer.consumer_key for consumer in page.consumers}
    assert len([path for path in reads if path.name == "definition.yaml"]) == 2
    assert all(path.name != "import.yaml" for path in reads)
    assert page.definition_file_count == 2
    assert page.continuation.startswith("character:v1:2:")
    assert "ab-health-xianxia" not in page.continuation
    assert {target.canonical_identity for target in page.targets} == {
        f"character:{TEST_CAMPAIGN_SLUG}:aa-health-dnd",
        f"character:{TEST_CAMPAIGN_SLUG}:ab-health-xianxia",
    }
    assert {
        key.partition(":")[2]
        for key in consumer_keys
        if key.startswith("aa-health-dnd:")
    } == {
        "profile.classes[0].systems_ref",
        "profile.classes[0].subclass_ref",
        "profile.species_ref",
        "profile.background_ref",
        "profile.species_page_ref",
        "profile.background_page_ref",
        "features[0].systems_ref",
        "features[0].page_ref",
        "spellcasting.spells[0].systems_ref",
        "spellcasting.spells[0].page_ref",
        "equipment_catalog[0].systems_ref",
        "equipment_catalog[0].page_ref",
    }
    assert {
        key.partition(":")[2]
        for key in consumer_keys
        if key.startswith("ab-health-xianxia:")
    } == {
        "xianxia.martial_arts[0].systems_ref",
        "xianxia.generic_techniques[0].systems_ref",
        "xianxia.equipment.necessary_weapons[0].systems_ref",
        "xianxia.equipment.necessary_tools[0].systems_ref",
    }
    assert metrics["query_count"] == 0
    assert repository._character_payload_cache == character_cache_before
    assert repository._campaign_config_cache == config_cache_before


def test_character_inventory_continuation_uses_the_complete_mixed_case_total_order(app):
    repository = app.extensions["character_repository"]
    characters_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / TEST_CAMPAIGN_SLUG
        / "characters"
    )
    def write_character(character_slug: str) -> None:
        character_dir = characters_dir / character_slug
        character_dir.mkdir(parents=True, exist_ok=True)
        (character_dir / "definition.yaml").write_text(
            yaml.safe_dump(
                {
                    "campaign_slug": TEST_CAMPAIGN_SLUG,
                    "character_slug": character_slug,
                    "status": "active",
                    "system": "DND-5E",
                    "profile": {},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    for character_slug in ("zeta-mixed", "Zulu-mixed"):
        write_character(character_slug)

    continuation = ""
    emitted: list[str] = []
    seen_continuations: set[str] = set()
    inserted_around_cursor = False
    while True:
        page = repository.list_source_health_consumers(
            TEST_CAMPAIGN_SLUG,
            continuation=continuation,
            limit=1,
        )
        emitted.extend(
            target.canonical_identity.rpartition(":")[2]
            for target in page.targets
        )
        if not page.continuation:
            break
        assert page.continuation not in seen_continuations
        assert "zeta-mixed" not in page.continuation
        assert "Zulu-mixed" not in page.continuation
        seen_continuations.add(page.continuation)
        continuation = page.continuation
        if emitted[-1] == "zeta-mixed" and not inserted_around_cursor:
            # Moving the numeric position proves continuation is driven by the
            # validated prior total-order key and a strict `>` filter.
            write_character("Aardvark-added-after-cursor")
            write_character("zulu-new-after-cursor")
            inserted_around_cursor = True

    assert emitted == sorted(emitted, key=lambda slug: (slug.casefold(), slug))
    assert "Aardvark-added-after-cursor" not in emitted
    assert emitted.count("zeta-mixed") == 1
    assert emitted.count("Zulu-mixed") == 1
    assert emitted.count("zulu-new-after-cursor") == 1


def test_character_exact_resolver_is_immutable_deduped_measured_and_maps_outcomes(app, monkeypatch):
    repository = app.extensions["character_repository"]
    characters_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / TEST_CAMPAIGN_SLUG
        / "characters"
    )

    def write_definition(slug, *, status="active", identity_slug=None, campaign_slug=TEST_CAMPAIGN_SLUG):
        character_dir = characters_dir / slug
        character_dir.mkdir(parents=True, exist_ok=True)
        definition_path = character_dir / "definition.yaml"
        definition_path.write_text(
            yaml.safe_dump(
                {
                    "campaign_slug": campaign_slug,
                    "character_slug": identity_slug or slug,
                    "status": status,
                    "system": "DND-5E",
                    "profile": {},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return definition_path

    active_path = write_definition("exact-active")
    inactive_path = write_definition("exact-inactive", status="inactive")
    mismatch_path = write_definition("exact-mismatch", identity_slug="other-slug")
    campaign_mismatch_path = write_definition(
        "exact-campaign-mismatch",
        campaign_slug="other-campaign",
    )
    active_ref = SourceHealthReference("character", target_id="exact-active")
    active_alias_ref = SourceHealthReference("character", slug="exact-active")
    inactive_ref = SourceHealthReference("character", target_id="exact-inactive")
    mismatch_ref = SourceHealthReference("character", target_id="exact-mismatch")
    campaign_mismatch_ref = SourceHealthReference(
        "character",
        target_id="exact-campaign-mismatch",
    )
    absent_ref = SourceHealthReference("character", target_id="exact-absent")
    successful_reads: list[Path] = []
    original_read_bytes = Path.read_bytes

    def tracked_read_bytes(path):
        payload = original_read_bytes(path)
        if path.name == "definition.yaml":
            successful_reads.append(path)
        return payload

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    batch = repository.resolve_source_health_character_targets(
        TEST_CAMPAIGN_SLUG,
        (
            active_ref,
            active_alias_ref,
            inactive_ref,
            mismatch_ref,
            campaign_mismatch_ref,
            absent_ref,
        ),
    )

    assert batch.definition_file_count == 4
    assert batch.definition_bytes == sum(
        len(path.read_bytes())
        for path in (
            active_path,
            inactive_path,
            mismatch_path,
            campaign_mismatch_path,
        )
    )
    assert successful_reads[:4] == [
        active_path,
        inactive_path,
        mismatch_path,
        campaign_mismatch_path,
    ]
    assert len([path for path in successful_reads[:4] if path == active_path]) == 1
    assert batch.resolutions[active_ref] == batch.resolutions[active_alias_ref]
    assert batch.resolutions[active_ref].targets[0].enabled is True
    assert batch.resolutions[inactive_ref].targets[0].enabled is False
    assert batch.resolutions[mismatch_ref].targets[0].accessible is False
    assert batch.resolutions[campaign_mismatch_ref].targets[0].accessible is False
    assert batch.resolutions[absent_ref] == SourceHealthResolution()
    with pytest.raises(TypeError):
        batch.resolutions[active_ref] = SourceHealthResolution()
    with pytest.raises(FrozenInstanceError):
        batch.definition_file_count = 99


def test_character_exact_resolver_invalid_conflicting_and_over_cap_refs_do_zero_io(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    invalid_refs = (
        SourceHealthReference("character", target_id="../escape"),
        SourceHealthReference("character", target_id="CON"),
        SourceHealthReference("character", target_id="hero", slug="other"),
        SourceHealthReference("character"),
    )
    monkeypatch.setattr(
        character_repository_module,
        "load_campaign_character_config",
        lambda *_: pytest.fail("invalid Character refs performed config I/O"),
    )
    monkeypatch.setattr(
        character_repository_module,
        "resolve_character_definition_import_paths",
        lambda *_: pytest.fail("invalid Character refs reached containment resolution"),
    )
    batch = repository.resolve_source_health_character_targets(
        TEST_CAMPAIGN_SLUG,
        invalid_refs,
    )
    assert batch.definition_file_count == 0
    assert batch.definition_bytes == 0
    assert all(batch.resolutions[reference] == SourceHealthResolution() for reference in invalid_refs)

    over_cap_refs = tuple(
        SourceHealthReference("character", target_id=f"valid-{index:02d}")
        for index in range(51)
    )
    with pytest.raises(ValueError, match="50"):
        repository.resolve_source_health_character_targets(
            TEST_CAMPAIGN_SLUG,
            over_cap_refs,
        )


def test_source_health_character_reads_invoke_containment_use_returned_paths_and_redact_rejection(
    tmp_path,
    monkeypatch,
):
    campaigns_dir = tmp_path / "campaigns"
    campaign_dir = campaigns_dir / "safe-campaign"
    characters_dir = campaign_dir / "characters"
    characters_dir.mkdir(parents=True)
    (campaign_dir / "campaign.yaml").write_text(
        yaml.safe_dump(
            {
                "slug": "safe-campaign",
                "system": "DND-5E",
                "character_dir": "characters",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for slug in ("mapped", "rejected", "unreadable"):
        character_dir = characters_dir / slug
        character_dir.mkdir()
        (character_dir / "definition.yaml").write_text(
            "PRIVATE PLACEHOLDER THAT MUST NOT BE READ",
            encoding="utf-8",
        )
    mapped_safe_path = characters_dir / "mapped" / "safe-definition.yaml"
    mapped_safe_path.write_text(
        yaml.safe_dump(
            {
                "campaign_slug": "safe-campaign",
                "character_slug": "mapped",
                "status": "active",
                "system": "DND-5E",
                "profile": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    unreadable_safe_path = characters_dir / "unreadable" / "safe-definition.yaml"
    unreadable_safe_path.write_text("unreadable", encoding="utf-8")
    repository = character_repository_module.CharacterRepository(campaigns_dir, object())
    original_resolve = character_repository_module.resolve_character_definition_import_paths
    helper_calls: list[str] = []

    def guarded_resolve(root, slug):
        helper_calls.append(slug)
        if slug == "rejected":
            raise CharacterPathSafetyError("private containment detail")
        if slug == "mapped":
            return mapped_safe_path, characters_dir / "mapped" / "safe-import.yaml"
        if slug == "unreadable":
            return unreadable_safe_path, characters_dir / "unreadable" / "safe-import.yaml"
        return original_resolve(root, slug)

    read_attempts: list[Path] = []
    original_read_bytes = Path.read_bytes

    def guarded_read(path):
        if path.name.endswith("definition.yaml"):
            read_attempts.append(path)
        if path == unreadable_safe_path:
            raise PermissionError("private read denial")
        return original_read_bytes(path)

    monkeypatch.setattr(
        character_repository_module,
        "resolve_character_definition_import_paths",
        guarded_resolve,
    )
    monkeypatch.setattr(Path, "read_bytes", guarded_read)

    page = repository.list_source_health_consumers("safe-campaign")
    refs = tuple(
        SourceHealthReference("character", target_id=slug)
        for slug in ("mapped", "rejected", "unreadable")
    )
    batch = repository.resolve_source_health_character_targets("safe-campaign", refs)

    assert helper_calls.count("mapped") == 2
    assert helper_calls.count("rejected") == 2
    assert helper_calls.count("unreadable") == 2
    assert read_attempts.count(mapped_safe_path) == 2
    assert read_attempts.count(unreadable_safe_path) == 2
    assert characters_dir / "mapped" / "definition.yaml" not in read_attempts
    assert characters_dir / "rejected" / "definition.yaml" not in read_attempts
    page_targets = {target.canonical_identity: target for target in page.targets}
    assert page_targets["character:safe-campaign:mapped"].accessible is True
    assert page_targets["character:safe-campaign:rejected"].accessible is False
    assert page_targets["character:safe-campaign:unreadable"].accessible is False
    assert batch.resolutions[refs[0]].targets[0].accessible is True
    assert batch.resolutions[refs[1]].targets[0].accessible is False
    assert batch.resolutions[refs[2]].targets[0].accessible is False
    assert page.definition_file_count == 1
    assert batch.definition_file_count == 1
    assert page.definition_bytes == len(mapped_safe_path.read_bytes())
    assert batch.definition_bytes == len(mapped_safe_path.read_bytes())


def test_source_health_character_inventory_and_exact_resolution_reject_physical_link_escapes(
    tmp_path,
    monkeypatch,
):
    campaigns_dir = tmp_path / "campaigns"
    campaign_dir = campaigns_dir / "link-campaign"
    characters_dir = campaign_dir / "characters"
    outside_dir = tmp_path / "outside-character"
    characters_dir.mkdir(parents=True)
    outside_dir.mkdir()
    (campaign_dir / "campaign.yaml").write_text(
        yaml.safe_dump(
            {
                "slug": "link-campaign",
                "system": "DND-5E",
                "character_dir": "characters",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    external_definition = outside_dir / "definition.yaml"
    external_definition.write_text(
        yaml.safe_dump(
            {
                "campaign_slug": "link-campaign",
                "character_slug": "link-dir",
                "status": "active",
                "system": "DND-5E",
                "profile": {},
            }
        ),
        encoding="utf-8",
    )
    file_link_dir = characters_dir / "link-file"
    file_link_dir.mkdir()
    try:
        (characters_dir / "link-dir").symlink_to(outside_dir, target_is_directory=True)
        (file_link_dir / "definition.yaml").symlink_to(external_definition)
    except OSError as exc:
        pytest.skip(f"physical links unavailable on this host: {exc}")

    reads: list[Path] = []
    original_read_bytes = Path.read_bytes

    def tracked_read(path):
        if path.name == "definition.yaml":
            reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", tracked_read)
    repository = character_repository_module.CharacterRepository(campaigns_dir, object())
    page = repository.list_source_health_consumers("link-campaign")
    refs = tuple(
        SourceHealthReference("character", target_id=slug)
        for slug in ("link-dir", "link-file")
    )
    batch = repository.resolve_source_health_character_targets("link-campaign", refs)

    targets = {target.canonical_identity: target for target in page.targets}
    assert targets["character:link-campaign:link-dir"].accessible is False
    assert targets["character:link-campaign:link-file"].accessible is False
    assert all(batch.resolutions[reference].targets[0].accessible is False for reference in refs)
    assert reads == []


@pytest.mark.parametrize(
    "payload",
    [b"\xffPRIVATE DECODE DETAIL", b"[not, an, object]", b"unterminated: ["],
)
def test_malformed_exact_character_definition_returns_only_sanitized_service_error(
    tmp_path,
    payload,
):
    campaigns_dir = tmp_path / "campaigns"
    campaign_dir = campaigns_dir / "malformed-campaign"
    character_dir = campaign_dir / "characters" / "malformed"
    character_dir.mkdir(parents=True)
    (campaign_dir / "campaign.yaml").write_text(
        yaml.safe_dump(
            {
                "slug": "malformed-campaign",
                "system": "DND-5E",
                "character_dir": "characters",
            }
        ),
        encoding="utf-8",
    )
    (character_dir / "definition.yaml").write_bytes(payload)
    repository = character_repository_module.CharacterRepository(campaigns_dir, object())
    reference = SourceHealthReference("character", target_id="malformed")
    consumer = SourceHealthConsumer(
        consumer_type="combatant",
        consumer_key="combatant:malformed",
        surface="Combat",
        reference=reference,
    )
    context = SourceHealthAccessContext(
        "malformed-campaign",
        "DND-5E",
        "DND-5E",
        False,
    )
    service = _service(
        authorize=lambda _slug: context,
        inventory_adapters=(
            ("characters", lambda *_: SourceHealthInventoryPage()),
            ("combat", lambda *_: SourceHealthInventoryPage(consumers=(consumer,))),
        ),
        resolver=lambda *_: {},
        character_resolver=lambda _context, references: repository.resolve_source_health_character_targets(
            "malformed-campaign",
            references,
        ),
    )

    report = service.build_report("malformed-campaign")
    assert report.state == "error"
    assert report.complete is False
    assert report.findings == ()
    assert report.message == "Source Health could not complete. Refresh to retry."
    assert "PRIVATE" not in report.message


def test_combat_and_dm_content_adapters_are_metadata_only_exact_and_campaign_scoped(app):
    with app.app_context():
        combat_store = CampaignCombatStore()
        dm_store = CampaignDMContentStore()
        statblock = dm_store.create_statblock(
            TEST_CAMPAIGN_SLUG,
            title="Private Statblock",
            body_markdown="PRIVATE STATBLOCK BODY",
            source_filename="private.md",
            subsection="Private",
            armor_class=12,
            max_hp=10,
            speed_text="30 ft.",
            movement_total=30,
            initiative_bonus=1,
        )
        foreign_statblock = dm_store.create_statblock(
            "other-campaign",
            title="Foreign Private Statblock",
            body_markdown="FOREIGN PRIVATE BODY",
            source_filename="foreign-private.md",
            subsection="Private",
            armor_class=13,
            max_hp=11,
            speed_text="30 ft.",
            movement_total=30,
            initiative_bonus=2,
        )
        for source_kind, source_ref in (
            ("systems_monster", "monster|PHB|goblin"),
            ("dm_statblock", str(statblock.id)),
            ("character", "arden-march"),
            ("manual_npc", "manual-ignored"),
            ("systems_monster", ""),
        ):
            combat_store.create_combatant(
                TEST_CAMPAIGN_SLUG,
                combatant_type="npc",
                display_name="PRIVATE DISPLAY NAME",
                source_kind=source_kind,
                source_ref=source_ref,
            )

        reset_db_query_metrics()
        page = combat_store.list_source_health_consumers(TEST_CAMPAIGN_SLUG)
        dm_reference = next(
            consumer.reference
            for consumer in page.consumers
            if consumer.reference.target_kind == "dm_statblock"
        )
        resolutions = dm_store.resolve_source_health_statblock_targets(
            TEST_CAMPAIGN_SLUG,
            (
                dm_reference,
                SourceHealthReference(
                    "dm_statblock",
                    target_id=str(foreign_statblock.id),
                ),
            ),
        )
        metrics = get_db_query_metrics()

    assert [consumer.reference.target_kind for consumer in page.consumers] == [
        "systems",
        "dm_statblock",
        "character",
    ]
    assert resolutions[dm_reference].targets[0].target_type == "dm_statblock"
    assert resolutions[
        SourceHealthReference("dm_statblock", target_id=str(foreign_statblock.id))
    ].targets == ()
    assert all("PRIVATE" not in json.dumps(consumer.reference.__dict__ if hasattr(consumer.reference, "__dict__") else str(consumer.reference)) for consumer in page.consumers)
    assert metrics["query_count"] == 2
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0


def test_systems_batch_is_exact_disabled_inclusive_and_avoids_seed_ensure_and_cache(
    app,
    monkeypatch,
):
    with app.app_context():
        store = SystemsStore()
        service = app.extensions["systems_service"]
        store.upsert_library("DND-5E", title="DND", system_code="DND-5E")
        store.upsert_source(
            "DND-5E",
            "QOL",
            title="QoL",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            "DND-5E",
            "QOL",
            entry_types=["item"],
            entries=[
                {
                    "entry_key": "item|qol|one",
                    "entry_type": "item",
                    "slug": "qol-one",
                    "title": "One",
                    "metadata": {
                        "campaign_item_mechanics_review_status": "draft",
                        "version": "2",
                        "version_scheme": "integer",
                    },
                    "body": {"secret": "PRIVATE BODY"},
                    "rendered_html": "<p>PRIVATE BODY</p>",
                },
                {
                    "entry_key": "item|qol|two",
                    "entry_type": "item",
                    "slug": "qol-two",
                    "title": "Two",
                    "metadata": {"rule_key": "armor-class"},
                    "body": {},
                    "rendered_html": "",
                },
            ],
        )
        store.upsert_library("XIANXIA", title="Xianxia", system_code="XIANXIA")
        store.upsert_source(
            "XIANXIA",
            "QOL",
            title="Xianxia QoL",
            license_class="custom_campaign",
            public_visibility_allowed=False,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            "XIANXIA",
            "QOL",
            entry_types=["item"],
            entries=[
                {
                    "entry_key": "item|qol|foreign",
                    "entry_type": "item",
                    "slug": "qol-foreign",
                    "title": "Foreign",
                    "metadata": {},
                    "body": {},
                    "rendered_html": "",
                }
            ],
        )
        store.upsert_source(
            "DND-5E",
            "RULES",
            title="Rules",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            "DND-5E",
            "RULES",
            entry_types=["rule"],
            entries=[
                {
                    "entry_key": "rule|rules|armor-class",
                    "entry_type": "rule",
                    "slug": "rules-armor-class",
                    "title": "Armor Class",
                    "metadata": {"rule_key": "armor-class"},
                    "body": {"secret": "PRIVATE RULE BODY"},
                    "rendered_html": "<p>PRIVATE RULE BODY</p>",
                }
            ],
        )
        store.upsert_campaign_enabled_source(
            TEST_CAMPAIGN_SLUG,
            library_slug="DND-5E",
            source_id="QOL",
            is_enabled=True,
            default_visibility="players",
        )
        store.upsert_campaign_entry_override(
            TEST_CAMPAIGN_SLUG,
            library_slug="DND-5E",
            entry_key="item|qol|one",
            visibility_override=None,
            is_enabled_override=False,
        )
        store.upsert_campaign_entry_override(
            TEST_CAMPAIGN_SLUG,
            library_slug="DND-5E",
            entry_key="item|qol|two",
            visibility_override="private",
            is_enabled_override=None,
        )
        disabled_ref = _reference(
            entry_key="item|qol|one",
            slug="",
            source_id="QOL",
            consumer_version="1",
            version_scheme="integer",
        )
        conflict_ref = _reference(
            entry_key="item|qol|one",
            slug="qol-two",
            source_id="QOL",
        )
        rule_ref = _reference(
            entry_key="",
            slug="",
            rule_key="Armor Class",
            source_id="RULES",
        )
        title_only_ref = _reference(
            entry_key="",
            slug="",
            rule_key="One",
            source_id="QOL",
        )
        private_ref = _reference(
            entry_key="item|qol|two",
            slug="",
            source_id="QOL",
        )
        wrong_system_ref = _reference(
            library_slug="XIANXIA",
            system_code="XIANXIA",
            entry_key="item|qol|foreign",
            slug="",
            source_id="QOL",
        )

        def forbidden(*_args, **_kwargs):
            pytest.fail("Source Health entered a seed, ensure, repository, or cache path")

        monkeypatch.setattr(service, "_get_campaign", forbidden)
        monkeypatch.setattr(service, "ensure_builtin_library_seeded", forbidden)
        monkeypatch.setattr(systems_service_module, "_systems_service_cache_get", forbidden)
        monkeypatch.setattr(systems_service_module, "_systems_service_cache_clear", forbidden)
        context = service.build_source_health_access_context(
            TEST_CAMPAIGN_SLUG,
            system_code="DND-5E",
            systems_library_slug="DND-5E",
            source_policy_defaults=(
                ("QOL", True, "players"),
                ("RULES", True, "players"),
            ),
            can_view_private=False,
        )
        assert context is not None

        reset_db_query_metrics()
        resolutions = service.resolve_source_health_targets(
            context,
            (
                disabled_ref,
                conflict_ref,
                rule_ref,
                title_only_ref,
                private_ref,
                wrong_system_ref,
            ),
        )
        metrics = get_db_query_metrics()
        reset_db_query_metrics()
        private_resolutions = service.resolve_source_health_targets(
            replace(context, can_view_private=True),
            (private_ref,),
        )
        private_metrics = get_db_query_metrics()
        reset_db_query_metrics()
        rule_alone = service.resolve_source_health_targets(context, (rule_ref,))
        rule_metrics = get_db_query_metrics()

    disabled_target = resolutions[disabled_ref].targets[0]
    assert disabled_target.enabled is False
    assert disabled_target.review_blocked is True
    assert disabled_target.target_version == "2"
    assert resolutions[conflict_ref].ambiguous is True
    assert resolutions[rule_ref].targets[0].canonical_identity.endswith(
        ":rule|rules|armor-class"
    )
    assert resolutions[rule_ref] == rule_alone[rule_ref]
    assert resolutions[title_only_ref].targets == ()
    assert resolutions[private_ref].targets[0].accessible is False
    assert private_resolutions[private_ref].targets[0].accessible is True
    assert resolutions[wrong_system_ref].targets[0].wrong_system is True
    assert metrics["query_count"] == 1
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0
    assert private_metrics["query_count"] == 1
    assert private_metrics["write_count"] == 0
    assert rule_metrics["query_count"] == 1
    assert rule_metrics["write_count"] == 0


def test_authorized_complete_healthy_service_is_bounded_and_read_only(app, monkeypatch):
    repository = app.extensions["character_repository"]
    characters_dir = (
        Path(app.config["TEST_CAMPAIGNS_DIR"])
        / TEST_CAMPAIGN_SLUG
        / "characters"
    )
    character_dir = characters_dir / "zz-health-only"
    character_dir.mkdir(parents=True, exist_ok=True)
    definition_path = character_dir / "definition.yaml"
    definition_path.write_text(
        yaml.safe_dump(
            {
                "campaign_slug": TEST_CAMPAIGN_SLUG,
                "character_slug": "zz-health-only",
                "status": "active",
                "system": "DND-5E",
                "profile": {},
                "equipment_catalog": [
                    {
                        "systems_ref": {
                            "library_slug": "DND-5E",
                            "entry_key": "item|qol|healthy-one",
                            "source_id": "QOL",
                        }
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    start_continuation = repository.list_source_health_consumers(
        TEST_CAMPAIGN_SLUG,
        limit=3,
    ).continuation
    assert start_continuation

    with app.app_context():
        store = SystemsStore()
        store.upsert_library("DND-5E", title="DND", system_code="DND-5E")
        store.upsert_source(
            "DND-5E",
            "QOL",
            title="QoL",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        store.replace_entries_for_source(
            "DND-5E",
            "QOL",
            entry_types=["item"],
            entries=[
                {
                    "entry_key": "item|qol|healthy-one",
                    "entry_type": "item",
                    "slug": "qol-healthy-one",
                    "title": "Healthy",
                    "metadata": {},
                    "body": {"secret": "PRIVATE BODY"},
                    "rendered_html": "<p>PRIVATE BODY</p>",
                }
            ],
        )
        store.upsert_campaign_enabled_source(
            TEST_CAMPAIGN_SLUG,
            library_slug="DND-5E",
            source_id="QOL",
            is_enabled=True,
            default_visibility="players",
        )
        context = SourceHealthAccessContext(TEST_CAMPAIGN_SLUG, "DND-5E", "DND-5E", False)
        reads: list[tuple[Path, int]] = []
        original_read_bytes = Path.read_bytes

        def tracked_read_bytes(path: Path) -> bytes:
            payload = original_read_bytes(path)
            if path.name in {"definition.yaml", "import.yaml"}:
                reads.append((path, len(payload)))
            return payload

        monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
        service = _service(
            authorize=lambda _slug: context,
            inventory_adapters=(
                (
                    "characters",
                    lambda _context, continuation: (
                        pytest.fail("unexpected composite adapter continuation")
                        if continuation
                        else repository.list_source_health_consumers(
                            TEST_CAMPAIGN_SLUG,
                            continuation=start_continuation,
                        )
                    ),
                ),
            ),
            resolver=lambda _context, references: store.resolve_source_health_targets(
                TEST_CAMPAIGN_SLUG,
                campaign_library_slug="DND-5E",
                campaign_system_code="DND-5E",
                references=references,
                default_source_policy={"QOL": (True, "players")},
            ),
        )

        reset_db_query_metrics()
        report = service.build_report(TEST_CAMPAIGN_SLUG)
        payload = serialize_source_health_report(report)
        metrics = get_db_query_metrics()

    definition_reads = [(path, size) for path, size in reads if path.name == "definition.yaml"]
    assert report.state == "healthy"
    assert report.complete is True
    assert len(report.findings) == 1
    assert len(payload) <= SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES
    assert report.measurements.definition_file_count == 1
    assert report.measurements.definition_bytes == definition_reads[0][1]
    assert len(definition_reads) == 1
    assert all(path.name != "import.yaml" for path, _ in reads)
    assert metrics["query_count"] == 1
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0


def test_authorized_worst_capped_service_measures_three_queries_fifty_definition_reads_and_no_writes(
    app,
    monkeypatch,
):
    repository = app.extensions["character_repository"]
    campaigns_dir = Path(app.config["TEST_CAMPAIGNS_DIR"])
    characters_dir = campaigns_dir / TEST_CAMPAIGN_SLUG / "characters"
    for index in range(51):
        character_slug = f"aa-health-{index:02d}"
        character_dir = characters_dir / character_slug
        character_dir.mkdir(parents=True, exist_ok=True)
        definition = {
            "campaign_slug": TEST_CAMPAIGN_SLUG,
            "character_slug": character_slug,
            "name": f"Health {index}",
            "status": "active",
            "system": "DND-5E",
            "profile": {},
            "equipment_catalog": [
                {
                    "id": "healthy-item",
                    "name": "Healthy item",
                    "systems_ref": {
                        "library_slug": "DND-5E",
                        "entry_key": "item|qol|healthy",
                        "slug": "qol-healthy",
                        "entry_type": "item",
                        "source_id": "QOL",
                    },
                }
            ],
        }
        (character_dir / "definition.yaml").write_text(
            yaml.safe_dump(definition, sort_keys=False),
            encoding="utf-8",
        )

    with app.app_context():
        systems_store = SystemsStore()
        systems_store.upsert_library("DND-5E", title="DND", system_code="DND-5E")
        systems_store.upsert_source(
            "DND-5E",
            "QOL",
            title="QoL",
            license_class="srd_cc",
            public_visibility_allowed=True,
            requires_unofficial_notice=False,
        )
        systems_store.replace_entries_for_source(
            "DND-5E",
            "QOL",
            entry_types=["item"],
            entries=[
                {
                    "entry_key": "item|qol|healthy",
                    "entry_type": "item",
                    "slug": "qol-healthy",
                    "title": "Healthy",
                    "metadata": {},
                    "body": {"secret": "PRIVATE BODY"},
                    "rendered_html": "<p>PRIVATE BODY</p>",
                }
            ],
        )
        systems_store.upsert_campaign_enabled_source(
            TEST_CAMPAIGN_SLUG,
            library_slug="DND-5E",
            source_id="QOL",
            is_enabled=True,
            default_visibility="players",
        )
        page_store = CampaignPageStore()
        combat_store = CampaignCombatStore()
        dm_store = CampaignDMContentStore()
        context = SourceHealthAccessContext(TEST_CAMPAIGN_SLUG, "DND-5E", "DND-5E", False)

        definition_reads: list[tuple[Path, int]] = []
        import_reads: list[Path] = []
        original_read_bytes = Path.read_bytes

        def tracked_read_bytes(path: Path) -> bytes:
            payload = original_read_bytes(path)
            if path.name == "definition.yaml":
                definition_reads.append((path, len(payload)))
            elif path.name == "import.yaml":
                import_reads.append(path)
            return payload

        monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
        character_cache_before = dict(repository._character_payload_cache)
        config_cache_before = dict(repository._campaign_config_cache)

        def resolve(_context, references):
            result = systems_store.resolve_source_health_targets(
                TEST_CAMPAIGN_SLUG,
                campaign_library_slug="DND-5E",
                campaign_system_code="DND-5E",
                references=references,
                default_source_policy={"QOL": (True, "players")},
            )
            result.update(page_store.resolve_source_health_page_targets(TEST_CAMPAIGN_SLUG, references))
            result.update(dm_store.resolve_source_health_statblock_targets(TEST_CAMPAIGN_SLUG, references))
            return result

        service = _service(
            authorize=lambda slug: context,
            inventory_adapters=(
                (
                    "characters",
                    lambda _context, continuation: repository.list_source_health_consumers(
                        TEST_CAMPAIGN_SLUG,
                        continuation=continuation,
                    ),
                ),
                (
                    "mechanics",
                    lambda _context, continuation: page_store.list_source_health_mechanics_consumers(
                        TEST_CAMPAIGN_SLUG,
                        continuation=continuation,
                    ),
                ),
                (
                    "combat",
                    lambda _context, continuation: combat_store.list_source_health_consumers(
                        TEST_CAMPAIGN_SLUG,
                        continuation=continuation,
                    ),
                ),
            ),
            resolver=resolve,
        )

        reset_db_query_metrics()
        report = service.build_report(TEST_CAMPAIGN_SLUG)
        payload = serialize_source_health_report(report)
        metrics = get_db_query_metrics()

    assert report.state == "partial"
    assert len(report.findings) == 50
    assert all(finding.classification == "healthy" for finding in report.findings)
    assert report.measurements.definition_file_count == 50
    assert report.measurements.definition_bytes == sum(size for _, size in definition_reads)
    assert len(definition_reads) == 50
    assert import_reads == []
    assert len(payload) <= 65_536
    assert metrics["query_count"] == 3
    assert metrics["write_count"] == 0
    assert metrics["commit_count"] == 0
    assert metrics["rollback_count"] == 0
    assert repository._character_payload_cache == character_cache_before
    assert repository._campaign_config_cache == config_cache_before


def test_serialized_payload_stays_bounded_for_fifty_maximum_length_findings():
    long_text = "x" * 2_000
    findings = tuple(
        SourceHealthFinding(
            consumer=SourceHealthConsumer(
                consumer_type=long_text,
                consumer_key=f"{index:02d}-{long_text}",
                surface=long_text,
                reference=_reference(entry_key=f"item|qol|{index}"),
                destination=long_text,
            ),
            classification="healthy",
            severity="healthy",
            action="none",
            target=SourceHealthTarget(
                target_kind=long_text,
                canonical_identity=f"{index:02d}-{long_text}",
                target_type=long_text,
                source_id=long_text,
                destination=long_text,
            ),
            destination=long_text,
        )
        for index in range(50)
    )
    report = SourceHealthReport(
        campaign_slug=long_text,
        state="healthy",
        findings=findings,
        continuations=(long_text,) * 3,
        message=long_text,
    )

    payload = serialize_source_health_report(report)

    assert len(payload) <= SOURCE_HEALTH_PAYLOAD_LIMIT_BYTES


def test_source_health_character_definition_reads_enforce_file_and_request_byte_caps(
    tmp_path,
):
    definition_path = tmp_path / "definition.yaml"
    definition_path.write_bytes(
        b"x" * (character_repository_module.SOURCE_HEALTH_DEFINITION_FILE_MAX_BYTES + 1)
    )
    with pytest.raises(ValueError, match="file cap"):
        character_repository_module._read_source_health_definition(
            definition_path,
            prior_bytes=0,
        )

    definition_path.write_bytes(b"safe: true\n")
    with pytest.raises(ValueError, match="request cap"):
        character_repository_module._read_source_health_definition(
            definition_path,
            prior_bytes=(
                character_repository_module.SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
            ),
        )

    with pytest.raises(ValueError, match="measurements"):
        SourceHealthResolutionBatch(
            definition_bytes=(
                character_repository_module.SOURCE_HEALTH_DEFINITION_AGGREGATE_MAX_BYTES
                + 1
            )
        )
