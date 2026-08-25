from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import inspect
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from urllib.request import urlopen

import pytest

import scripts.measure_character_read_performance as character_measurement
from scripts.measure_character_read_performance import (
    ACTORS,
    AsyncBrowserCollector,
    ARTIFACT_ORDER,
    ATTEMPT_SCHEDULE,
    ContractError,
    DIAGNOSTIC_COMPONENTS,
    EVIDENCE_RELATIVE_ROOT,
    EvidenceEnvelope,
    EvidenceRefusal,
    EXPECTED_BUSY_BODY_SHA256,
    FourWorkerWSGIServer,
    PRE_MANIFEST_ARTIFACTS,
    SCENARIOS,
    SCHEMA,
    SCRIPT_REPO_ROOT,
    VIEWPORTS,
    acceptance_contract,
    assert_candidate_import_boundary,
    browser_environment_identity,
    build_sample,
    build_unchanged_live_sample,
    build_attempt_schedule,
    classify_status,
    enforce_semantic_zero,
    environment_manifest,
    evaluate_baseline_freeze,
    extract_character_diagnostics,
    linear_percentile,
    materialize_git_object_fixture,
    normalize_diagnostics,
    privacy_findings,
    process_memory_snapshot,
    prove_git_object_fixture,
    require_clean_detached_git_identity,
    require_unchanged_git_identity,
    runtime_request_path,
    validate_run_id,
    validate_attempt_ledger,
    validate_expected_busy_response,
    validate_mutation_ledger,
)


def _asyncio():
    import asyncio

    return asyncio


def _sample(attempt, **changes):
    zero = attempt.zero_contract == "cache-no-network"
    diagnostics = {
        "route_class": "non-character" if zero else "character-document",
        "outcome": "not-applicable" if zero else "ok",
        "query_count": 0 if zero else 1,
        "response_bytes": 0 if zero else 100,
        "query_time_ms": 0.0 if zero else 0.5,
        **{component: 0.0 if zero else 1.0 for component in DIAGNOSTIC_COMPONENTS},
    }
    sample = build_sample(
        attempt,
        status_code=attempt.expected_statuses[0],
        network_request_count=0 if zero else 1,
        request_ms=0.0 if zero else 1.0,
        apply_ms=0.0,
        diagnostics=diagnostics,
        changed=False if attempt.zero_contract == "unchanged-live" else True,
        memory={"rss_bytes": 1, "peak_rss_bytes": 1},
    )
    sample.update(changes)
    if "status_code" in changes:
        classification = classify_status(attempt, changes["status_code"])
        sample["unexpected_error"] = classification["unexpected_error"]
        sample["expected_503"] = classification["expected_503"]
    return sample


def test_fixed_matrix_has_five_anonymous_actors_three_viewports_and_frozen_counts():
    assert [(actor.role, actor.writable) for actor in ACTORS] == [
        ("dm", True),
        ("player", True),
        ("player", False),
        ("observer", False),
        ("observer", False),
    ]
    assert [(viewport.width, viewport.height, viewport.javascript) for viewport in VIEWPORTS] == [
        (1280, 900, True),
        (390, 800, True),
        (1280, 900, False),
    ]
    ordinary = [scenario for scenario in SCENARIOS if scenario.pressure_group == "ordinary"]
    assert [
        (scenario.actor, scenario.surface, scenario.key)
        for scenario in ordinary
    ] == [
        ("dm", "session-character-fragment", "ordinary_session_fragment"),
        ("assigned_player", "normal-character", "ordinary_normal_read"),
        ("unassigned_player", "normal-character", "ordinary_normal_read"),
        ("observer_primary", "combat-live", "ordinary_combat_unchanged"),
        ("observer_secondary", "session-live", "ordinary_session_unchanged"),
    ]
    assert all(scenario.samples == 12 for scenario in ordinary)
    assert all(scenario.samples == 8 and scenario.warmups == 1 for scenario in SCENARIOS if scenario.key in {"normal_document", "normal_enhanced_section", "session_document", "session_section_fragment", "xianxia_normal_document", "xianxia_session_document"})
    assert all(scenario.samples == 12 for scenario in SCENARIOS if scenario.key in {"normal_visited_return", "session_section_cached_apply"})
    assert len([attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "session_mutation_post"]) == 6
    assert len([attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "session_mutation_redirect_get"]) == 6
    assert len([attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "overload_character_busy"]) == 3
    assert any(attempt.zero_contract != "none" for attempt in ATTEMPT_SCHEDULE)
    assert len(ATTEMPT_SCHEDULE) == 600
    assert {attempt.viewport for attempt in ATTEMPT_SCHEDULE} == {"desktop", "mobile", "no-js"}
    assert {scenario.section for scenario in SCENARIOS if scenario.key == "normal_document"} == set(
        ("quick", "spellcasting", "features", "equipment", "inventory", "notes", "controls")
    )
    assert {scenario.section for scenario in SCENARIOS if scenario.key == "session_document"} == set(
        ("overview", "spells", "resources", "features", "equipment", "inventory", "notes")
    )


def test_schedule_refuses_duplicate_scenario_and_bad_fixed_fields():
    with pytest.raises(ContractError, match="duplicate scenario cell"):
        build_attempt_schedule((SCENARIOS[0], SCENARIOS[0]))
    with pytest.raises(ContractError, match="unknown actor"):
        build_attempt_schedule((replace(SCENARIOS[0], actor="not-an-actor"),))
    with pytest.raises(ContractError, match="invalid sample count"):
        build_attempt_schedule((replace(SCENARIOS[0], samples=0),))


def test_runtime_route_builder_keeps_canonical_fragment_distinct_from_cached_apply():
    fragment = next(
        attempt for attempt in ATTEMPT_SCHEDULE
        if attempt.scenario == "session_section_fragment"
    )
    cached = next(
        attempt for attempt in ATTEMPT_SCHEDULE
        if attempt.scenario == "session_section_cached_apply"
    )
    assert "fragment=1" in runtime_request_path(fragment)
    assert "fragment=1" not in runtime_request_path(cached)
    ordinary_fragment = next(
        attempt
        for attempt in ATTEMPT_SCHEDULE
        if attempt.scenario == "ordinary_session_fragment"
    )
    assert "fragment=1" in runtime_request_path(ordinary_fragment)
    assert "page=overview" in runtime_request_path(ordinary_fragment)
    assert "page=quick" in runtime_request_path(
        next(attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "normal_document")
    )

    async def collect_cached_apply(section: str):
        attempt = next(
            attempt
            for attempt in ATTEMPT_SCHEDULE
            if attempt.scenario == "session_section_cached_apply"
            and attempt.section == section
        )
        trace = []
        cached_sections = {"overview"}

        class FakeContext:
            async def close(self):
                trace.append(("close",))

        class FakeResponse:
            status = 200

        class FakePage:
            def __init__(self):
                self.request_listener = None

            async def goto(self, url, *, wait_until):
                trace.append(("goto", "overview", wait_until))
                assert "page=overview" in url
                return FakeResponse()

            def on(self, event, listener):
                assert event == "request"
                assert self.request_listener is None
                self.request_listener = listener
                trace.append(("listen", event))

            def remove_listener(self, event, listener):
                assert event == "request"
                if self.request_listener is listener:
                    self.request_listener = None
                    trace.append(("unlisten", event))

        page = FakePage()
        context = FakeContext()
        collector = object.__new__(AsyncBrowserCollector)
        collector._base_url = "http://127.0.0.1:43123"

        async def fresh_page(_attempt):
            return context, page

        async def click_session_section(_page, target):
            trace.append(("click", target))
            if target not in cached_sections:
                cached_sections.add(target)
                if page.request_listener is not None:
                    page.request_listener(
                        SimpleNamespace(
                            method="GET",
                            url=(
                                "http://127.0.0.1:43123/campaigns/linden-pass/"
                                f"session/character?character=arden-march&page={target}&fragment=1"
                            ),
                        )
                    )

        async def wait_session_section(_page, target):
            assert target in cached_sections
            trace.append(("wait", target))

        collector._fresh_page = fresh_page
        collector._click_session_section = click_session_section
        collector._wait_session_section = wait_session_section
        sample = await collector.collect_session_cached_apply(attempt)
        return sample, trace

    resources_sample, resources_trace = _asyncio().run(collect_cached_apply("resources"))
    assert resources_sample["status_code"] == 200
    assert resources_sample["network_request_count"] == 0
    assert resources_trace[:7] == [
        ("goto", "overview", "domcontentloaded"),
        ("wait", "overview"),
        ("click", "resources"),
        ("wait", "resources"),
        ("click", "overview"),
        ("wait", "overview"),
        ("listen", "request"),
    ]
    assert resources_trace[7:9] == [("click", "resources"), ("wait", "resources")]

    overview_sample, overview_trace = _asyncio().run(collect_cached_apply("overview"))
    assert overview_sample["status_code"] == 200
    assert overview_sample["network_request_count"] == 0
    assert overview_trace[:5] == [
        ("goto", "overview", "domcontentloaded"),
        ("wait", "overview"),
        ("click", "spells"),
        ("wait", "spells"),
        ("listen", "request"),
    ]
    assert overview_trace[5:7] == [("click", "overview"), ("wait", "overview")]


def test_linear_percentile_is_inclusive_linear_and_strict():
    assert linear_percentile([0, 10], 50) == 5.0
    assert linear_percentile([1, 2, 3, 4, 5], 95) == pytest.approx(4.8)
    with pytest.raises(ContractError, match="JSON number"):
        linear_percentile([1, "2"], 50)
    with pytest.raises(ContractError, match="at least one"):
        linear_percentile([], 50)
    with pytest.raises(ContractError, match="at most"):
        linear_percentile([1], 101)


def test_diagnostics_require_exact_finite_nonnegative_numeric_fields():
    payload = {
        "route_class": "character-document",
        "outcome": "ok",
        "query_count": 3,
        "response_bytes": 500,
        **{component: 1.25 for component in DIAGNOSTIC_COMPONENTS},
    }
    assert normalize_diagnostics(payload)["query_count"] == 3
    with pytest.raises(ContractError, match="fields differ"):
        normalize_diagnostics({**payload, "raw_headers": "forbidden"})
    with pytest.raises(ContractError, match="integer"):
        normalize_diagnostics({**payload, "query_count": 3.0})
    with pytest.raises(ContractError, match="finite"):
        normalize_diagnostics({**payload, "total": float("nan")})


def test_raw_diagnostic_headers_are_strictly_extracted_to_semantic_values():
    headers = {
        "X-Character-Read-Route": "character-document",
        "X-Character-Read-Outcome": "ok",
        "X-Character-Read-Query-Count": "3",
        "X-Character-Read-Query-Time-Ms": "1.25",
        "X-Character-Read-Response-Bytes": "500",
        **{
            f"X-Character-Read-{'-'.join(part.title() for part in component.split('-'))}-Ms": (
                "1.25" if component == "db" else "2.50"
            )
            for component in DIAGNOSTIC_COMPONENTS
        },
    }
    parsed = extract_character_diagnostics(headers)
    assert parsed["route_class"] == "character-document"
    assert parsed["query_count"] == 3
    assert parsed["query_time_ms"] == 1.25
    assert "headers" not in parsed
    with pytest.raises(ContractError, match="numeric header"):
        extract_character_diagnostics({**headers, "X-Character-Read-Total-Ms": "nan"})
    with pytest.raises(ContractError, match="differ"):
        extract_character_diagnostics({**headers, "X-Character-Read-Query-Time-Ms": "1.26"})


def test_expected_503_is_only_the_normal_character_overload_attempt():
    overload = next(attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "overload_character_busy")
    assert classify_status(overload, 503) == {
        "status_code": 503,
        "expected": True,
        "expected_503": True,
        "unexpected_error": False,
    }
    ordinary = next(attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "normal_document")
    assert classify_status(ordinary, 503)["unexpected_error"] is True
    disguised = replace(overload, surface="session-character")
    assert classify_status(disguised, 503)["unexpected_error"] is True


def test_real_busy_response_requires_private_generic_admission_contract():
    headers = {
        "Retry-After": "2",
        "Cache-Control": "private, no-store",
        "X-Character-Read-Route": "character-document",
        "X-Character-Read-Outcome": "admission-503",
        "X-Character-Read-Query-Count": "0",
        "X-Character-Read-Query-Time-Ms": "0.00",
        "X-Character-Read-Response-Bytes": "317",
        **{
            f"X-Character-Read-{'-'.join(part.title() for part in component.split('-'))}-Ms": "0.00"
            for component in DIAGNOSTIC_COMPONENTS
        },
    }
    body = """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Character page busy</title></head>
  <body><main><h1>Character pages are busy</h1><p>Please wait a moment, then try opening this character section again.</p></main></body>
</html>"""
    assert len(body.encode("utf-8")) == 317
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == EXPECTED_BUSY_BODY_SHA256
    diagnostic = validate_expected_busy_response(
        503,
        headers,
        body,
        private_markers=("fixture-private",),
    )
    assert diagnostic["outcome"] == "admission-503"
    with pytest.raises(ContractError, match="private fixture"):
        validate_expected_busy_response(
            503,
            headers,
            body + " fixture-private",
            private_markers=("fixture-private",),
        )
    with pytest.raises(ContractError, match="private no-store"):
        validate_expected_busy_response(
            503,
            {**headers, "Cache-Control": "public"},
            body,
        )
    with pytest.raises(ContractError, match="private no-store"):
        validate_expected_busy_response(
            503,
            {**headers, "Cache-Control": "no-store"},
            body,
        )
    with pytest.raises(ContractError, match="generic body"):
        validate_expected_busy_response(
            503,
            headers,
            body.replace("Please wait a moment", "Please wait"),
        )


def test_semantic_zero_refuses_any_render_or_network_work():
    attempt = next(attempt for attempt in ATTEMPT_SCHEDULE if attempt.zero_contract == "cache-no-network")
    enforce_semantic_zero(attempt, _sample(attempt))
    for field in ("network_request_count", "server_ms", "query_count", "query_time_ms", "response_bytes"):
        with pytest.raises(ContractError, match=field):
            enforce_semantic_zero(attempt, _sample(attempt, **{field: 1}))


def test_live_normalizer_discards_tokens_and_raw_timing_before_retention():
    attempt = next(
        attempt for attempt in ATTEMPT_SCHEDULE
        if attempt.scenario == "ordinary_session_unchanged"
    )
    sample = build_unchanged_live_sample(
        attempt,
        {
            "changed": False,
            "requestMs": 12.5,
            "applyMs": 0.0,
            "payloadBytes": 42,
            "queryCount": 1,
            "queryTimeMs": 0.5,
            "requestTimeMs": 2.0,
            "liveRevision": 999,
            "liveViewToken": "private-token",
            "serverTiming": "raw-private-value",
        },
        memory={"rss_bytes": 10, "peak_rss_bytes": 20},
    )
    assert sample["changed"] is False
    assert sample["server_ms"] == 2.0
    assert sample["response_bytes"] == 42
    assert "liveRevision" not in sample
    assert "liveViewToken" not in sample
    assert "serverTiming" not in sample
    with pytest.raises(ContractError, match="not unchanged"):
        build_unchanged_live_sample(
            attempt,
            {
                "changed": True,
                "requestMs": 1.0,
                "applyMs": 0.0,
                "payloadBytes": 1,
                "queryCount": 0,
                "queryTimeMs": 0.0,
                "requestTimeMs": 1.0,
            },
            memory={"rss_bytes": 10, "peak_rss_bytes": 20},
        )


def test_attempt_ledger_refuses_missing_extra_duplicate_and_fixed_field_drift():
    schedule = ATTEMPT_SCHEDULE[:2]
    samples = [_sample(attempt) for attempt in schedule]
    assert validate_attempt_ledger(samples, schedule) == tuple(samples)
    with pytest.raises(ContractError, match="missing"):
        validate_attempt_ledger(samples[:1], schedule)
    with pytest.raises(ContractError, match="extra"):
        validate_attempt_ledger([*samples, {**samples[0], "attempt_id": "extra"}], schedule)
    with pytest.raises(ContractError, match="duplicates"):
        validate_attempt_ledger([samples[0], samples[0], samples[1]], schedule)
    with pytest.raises(ContractError, match="changed fixed field actor"):
        validate_attempt_ledger([{**samples[0], "actor": "dm" if schedule[0].actor != "dm" else "player-primary"}, samples[1]], schedule)


def test_mutation_ledger_requires_exactly_one_post_and_separate_redirect_get():
    post_attempt = next(attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "session_mutation_post")
    get_attempt = next(attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "session_mutation_redirect_get")
    post = _sample(post_attempt, status_code=302)
    redirected_get = _sample(get_attempt, status_code=200)
    assert validate_mutation_ledger([post, redirected_get]) == (post, redirected_get)
    with pytest.raises(ContractError, match="POST and its separate"):
        validate_mutation_ledger([post])
    with pytest.raises(ContractError, match="begin"):
        validate_mutation_ledger([redirected_get, post])
    with pytest.raises(ContractError, match="separate attempts"):
        validate_mutation_ledger([post, {**redirected_get, "attempt_id": post["attempt_id"]}])


def test_runtime_mutation_uses_mounted_page_transport_without_request_context_or_reload():
    source = inspect.getsource(AsyncBrowserCollector.collect_mutations)
    assert "context.request.post(" not in source
    assert "context.request.get(" not in source
    assert "page.set_content(" not in source
    assert "input_locator.blur()" in source
    assert 'page.on("request"' in source
    assert 'page.on("response"' in source
    assert 'page.on("domcontentloaded"' in source
    assert "get_request.redirected_from is not post_request" in source
    assert source.count("is_navigation_request()") == 2
    assert "__characterReadHarnessMountProof" in source
    assert "__characterReadHarnessSubmitAudit" in source
    assert "without retry" in source


def test_runtime_mutation_mounts_lazy_session_pane_before_measurement(monkeypatch):
    async def exercise_adapter(*, initially_mounted: bool, duplicate_get: bool = False):
        trace: list[tuple[object, ...]] = []

        class Request:
            method = "GET"
            url = "http://127.0.0.1:43123/campaigns/linden-pass/session?fragment=1"

            @staticmethod
            def is_navigation_request():
                return False

        request = Request()

        class Response:
            status = 200

            def __init__(self):
                self.request = request
                self.url = request.url

            @staticmethod
            async def all_headers():
                return {"cache-control": "private, no-store"}

        response = Response()

        class ResponseInfo:
            def __init__(self, predicate):
                self.predicate = predicate
                self.response = None

            async def __aenter__(self):
                trace.append(("expect-enter",))
                page.response_info = self
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                page.response_info = None

            @property
            def value(self):
                async def resolve():
                    assert self.response is response
                    return response

                return resolve()

        class CandidateLocator:
            def __init__(self, count, first):
                self._count = count
                self._first = first

            async def count(self):
                return self._count() if callable(self._count) else self._count

            @property
            def first(self):
                return self._first

        class LiveRoot:
            async def wait_for(self, *, state, timeout):
                trace.append(("live-wait", state, timeout))
                assert page.session_loaded is True

        live_root = LiveRoot()

        class SessionPane:
            def locator(self, selector):
                assert selector == (
                    "[data-session-live-root][data-session-live-view='session']"
                )
                return CandidateLocator(
                    lambda: 1 if page.session_loaded else 0,
                    live_root,
                )

            async def get_attribute(self, name):
                assert name == "data-session-shell-pane-loaded"
                return "1" if page.session_loaded else "0"

        session_pane = SessionPane()

        class SwitchLink:
            def __init__(self, target):
                self.target = target

            async def click(self):
                trace.append(("click", self.target))
                page.active_target = self.target
                if self.target != "session":
                    return
                page.session_loaded = True
                for callback in list(page.request_listeners):
                    callback(request)
                    if duplicate_get:
                        callback(request)
                assert page.response_info is not None
                assert page.response_info.predicate(response) is True
                page.response_info.response = response

        class ActiveCharacterShell:
            async def wait_for(self, *, state, timeout):
                trace.append(("character-wait", state, timeout))
                assert page.active_target == "character"

        class ActiveSessionShell:
            async def wait_for(self, *, state, timeout):
                trace.append(("session-wait", state, timeout))
                assert page.active_target == "session"

        class Page:
            def __init__(self):
                self.session_loaded = initially_mounted
                self.active_target = "character"
                self.request_listeners = []
                self.response_info = None

            def locator(self, selector):
                if selector == "[data-session-shell-pane='session']":
                    return CandidateLocator(1, session_pane)
                if selector == (
                    "[data-session-switch='1'][data-session-switch-target='session']"
                ):
                    return CandidateLocator(1, SwitchLink("session"))
                if selector == (
                    "[data-session-switch='1'][data-session-switch-target='character']"
                ):
                    return CandidateLocator(1, SwitchLink("character"))
                if selector == (
                    "[data-session-shell-root][data-session-shell-active='character']"
                ):
                    return ActiveCharacterShell()
                if selector == (
                    "[data-session-shell-root][data-session-shell-active='session']"
                ):
                    return ActiveSessionShell()
                raise AssertionError(f"unexpected selector: {selector}")

            def expect_response(self, predicate, *, timeout):
                trace.append(("expect-response", timeout))
                return ResponseInfo(predicate)

            def on(self, event, callback):
                assert event == "request"
                trace.append(("listener-add", event))
                self.request_listeners.append(callback)

            def remove_listener(self, event, callback):
                assert event == "request"
                trace.append(("listener-remove", event))
                self.request_listeners.remove(callback)

        page = Page()
        collector = AsyncBrowserCollector(
            "http://127.0.0.1:43123",
            SimpleNamespace(),
            None,
        )

        async def wait_for_section(candidate_page, section):
            assert candidate_page is page
            trace.append(("section-wait", section))

        monkeypatch.setattr(
            AsyncBrowserCollector,
            "_wait_session_section",
            staticmethod(wait_for_section),
        )
        await collector._ensure_session_live_pane_mounted_for_mutations(
            page,
            section="resources",
        )
        return trace

    legacy_trace = _asyncio().run(exercise_adapter(initially_mounted=True))
    assert legacy_trace == [("live-wait", "attached", 15000)]

    lazy_trace = _asyncio().run(exercise_adapter(initially_mounted=False))
    assert lazy_trace.count(("click", "session")) == 1
    assert lazy_trace.count(("click", "character")) == 1
    assert lazy_trace.count(("listener-add", "request")) == 1
    assert lazy_trace.count(("listener-remove", "request")) == 1
    assert lazy_trace.count(("section-wait", "resources")) == 1
    assert lazy_trace.index(("listener-remove", "request")) < lazy_trace.index(
        ("section-wait", "resources")
    )

    with pytest.raises(ContractError, match="exactly one setup Session GET"):
        _asyncio().run(exercise_adapter(initially_mounted=False, duplicate_get=True))

    helper_source = inspect.getsource(
        AsyncBrowserCollector._ensure_session_live_pane_mounted_for_mutations
    )
    mutation_source = inspect.getsource(AsyncBrowserCollector.collect_mutations)
    assert "perf_counter" not in helper_source
    assert "ATTEMPT_SCHEDULE" not in helper_source
    assert mutation_source.index(
        "_ensure_session_live_pane_mounted_for_mutations"
    ) < mutation_source.index("for post_attempt, get_attempt")
    assert mutation_source.index(
        "_ensure_session_live_pane_mounted_for_mutations"
    ) < mutation_source.index("__characterReadHarnessSubmitAudit")
    assert len(
        [attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "session_mutation_post"]
    ) == 6
    assert len(
        [
            attempt
            for attempt in ATTEMPT_SCHEDULE
            if attempt.scenario == "session_mutation_redirect_get"
        ]
    ) == 6


def test_runtime_mutation_session_section_locator_adapter_supports_both_vocabularies():
    async def exercise_adapter(
        vocabulary: str,
        *,
        link_count: int = 1,
        root_count: int = 1,
    ):
        trace = []
        section = "resources"
        leaf = SimpleNamespace()

        async def wait_for(*, state, timeout):
            trace.append(("wait", vocabulary, state, timeout))

        async def click():
            trace.append(("click", vocabulary))

        leaf.wait_for = wait_for
        leaf.click = click

        class CandidateLocator:
            def __init__(self, count, first):
                self._count = count
                self._first = first

            async def count(self):
                trace.append(("count", self._count))
                return self._count

            @property
            def first(self):
                trace.append(("first",))
                return self._first

        class Sheet:
            def locator(self, selector):
                trace.append(("sheet-locator", selector))
                if "toggle" in selector or "section-link" in selector:
                    assert selector == (
                        f"[data-combat-section-toggle='{section}'], "
                        f"[data-session-character-section-link='{section}']"
                    )
                    return CandidateLocator(link_count, leaf)
                assert selector == (
                    f"[data-combat-section-panel='{section}']:not([hidden]), "
                    "[data-session-character-section-root]"
                    f"[data-session-character-section='{section}']:not([hidden])"
                )
                return CandidateLocator(root_count, leaf)

        sheet = Sheet()

        async def wait_for_sheet(*, state, timeout):
            trace.append(("sheet-wait", state, timeout))

        sheet.wait_for = wait_for_sheet

        class Page:
            def __init__(self):
                self.out_of_scope_combat_decoy_selected = False

            def locator(self, selector):
                trace.append(("page-locator", selector))
                if selector != (
                    "[data-session-shell-pane='character']:not([hidden]) "
                    ".session-character-sheet[data-combat-workspace-root]"
                ):
                    self.out_of_scope_combat_decoy_selected = True
                    raise AssertionError("section lookup escaped the mounted Session character sheet")
                return CandidateLocator(1, sheet)

        page = Page()
        await AsyncBrowserCollector._click_session_section(page, section)
        await AsyncBrowserCollector._wait_session_section(page, section)
        return page, trace

    for vocabulary in ("legacy", "selected-section"):
        page, trace = _asyncio().run(exercise_adapter(vocabulary))
        assert page.out_of_scope_combat_decoy_selected is False
        assert ("click", vocabulary) in trace
        assert ("wait", vocabulary, "visible", 15000) in trace

    with pytest.raises(ContractError, match="exactly one"):
        _asyncio().run(exercise_adapter("ambiguous", link_count=2))
    with pytest.raises(ContractError, match="exactly one"):
        _asyncio().run(exercise_adapter("ambiguous", root_count=2))


@pytest.mark.parametrize(
    "location",
    [
        "/campaigns/linden-pass/session/character?character=arden-march&fragment=1",
        "/campaigns/linden-pass/session/character?character=arden-march&page=overview&fragment=1",
        "/campaigns/linden-pass/session/character?character=arden-march&character=arden-march&page=resources&fragment=1",
        "/campaigns/linden-pass/session/character?character=arden-march&page=resources&fragment=1&extra=1",
        "/campaigns/linden-pass/session/character?character=other&page=resources&fragment=1",
        "/campaigns/linden-pass/session/character?character=arden-march&page=resources&fragment=1&fragment=1",
    ],
)
def test_runtime_mutation_redirect_refuses_missing_wrong_duplicate_and_extra_query(location):
    collector = AsyncBrowserCollector("http://127.0.0.1:43123", SimpleNamespace(), None)
    canonical = (
        "/campaigns/linden-pass/session/character"
        "?character=arden-march&page=resources&fragment=1"
    )
    assert collector._validated_mutation_redirect(canonical + "#session-vitals").endswith(
        "#session-vitals"
    )
    with pytest.raises(ContractError, match="escaped"):
        collector._validated_mutation_redirect(
            "https://example.invalid/campaigns/linden-pass/session/character?fragment=1"
        )
    with pytest.raises(ContractError, match="canonical"):
        collector._validated_mutation_redirect(location)


def test_privacy_scan_reports_only_semantic_codes_and_locations():
    assert privacy_findings({"actor": "player-primary", "server_ms": 1.0}) == ()
    findings = privacy_findings(
        {
            "url": "https://127.0.0.1/private",
            "nested": {"email": "private@example.com"},
            "exception": "C:\\private\\trace.txt",
        }
    )
    assert {finding["code"] for finding in findings} >= {
        "forbidden-field",
        "url",
        "ipv4",
        "email",
        "windows-path",
    }
    assert all("private" not in str(finding) for finding in findings)


def test_git_identity_requires_exact_registered_clean_detached_checkout(tmp_path: Path):
    root = tmp_path.resolve()
    root.mkdir(exist_ok=True)
    responses = {
        ("rev-parse", "--show-toplevel"): (0, f"{root}\n"),
        ("symbolic-ref", "-q", "HEAD"): (1, ""),
        ("status", "--porcelain=v1", "--untracked-files=all"): (0, ""),
        ("rev-parse", "HEAD"): (0, "a" * 40 + "\n"),
        ("rev-parse", "HEAD^{tree}"): (0, "b" * 40 + "\n"),
        ("worktree", "list", "--porcelain"): (0, f"worktree {root}\nHEAD {'a' * 40}\ndetached\n"),
    }

    def runner(_root, *arguments):
        code, stdout = responses[arguments]
        return SimpleNamespace(returncode=code, stdout=stdout, stderr="")

    identity = require_clean_detached_git_identity(root, runner=runner)
    assert identity == {"commit": "a" * 40, "tree": "b" * 40, "checkout": "detached-clean-registered"}

    responses[("status", "--porcelain=v1", "--untracked-files=all")] = (0, "?? leak.txt\n")
    with pytest.raises(ContractError, match="clean worktree"):
        require_clean_detached_git_identity(root, runner=runner)


def test_publish_boundary_rechecks_exact_initial_git_identity_before_envelope(tmp_path: Path):
    initial = {
        "commit": "a" * 40,
        "tree": "b" * 40,
        "checkout": "detached-clean-registered",
    }
    calls = []

    def same_identity(root):
        calls.append(root)
        return dict(initial)

    assert require_unchanged_git_identity(
        tmp_path,
        initial,
        checker=same_identity,
    ) == initial
    assert calls == [tmp_path]
    with pytest.raises(ContractError, match="changed before publication"):
        require_unchanged_git_identity(
            tmp_path,
            initial,
            checker=lambda _root: {**initial, "tree": "c" * 40},
        )
    source = inspect.getsource(character_measurement.publish_baseline_evidence)
    assert source.index("require_unchanged_git_identity") < source.index("EvidenceEnvelope")


def test_git_object_fixture_proof_uses_tree_listing_and_blob_objects(tmp_path: Path):
    root = tmp_path.resolve()
    root.mkdir(exist_ok=True)
    object_id = "c" * 40
    calls = []

    def runner(_root, *arguments):
        calls.append(arguments)
        if arguments[0] == "ls-tree":
            return SimpleNamespace(
                returncode=0,
                stdout=f"100644 blob {object_id}\ttests/fixtures/sample_campaigns/linden-pass/campaign.yaml\0",
                stderr="",
            )
        assert arguments == ("cat-file", "-e", f"{object_id}^{{blob}}")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    proof = prove_git_object_fixture(root, runner=runner)
    assert proof["source"] == "git-object"
    assert proof["file_count"] == 1
    assert len(proof["fixture_digest"]) == 64
    assert calls[0][0] == "ls-tree" and calls[1][0] == "cat-file"


def test_git_object_fixture_materialization_reads_only_listed_blobs(tmp_path: Path):
    root = tmp_path.resolve()
    destination = tmp_path / "materialized"
    first_id = "d" * 40
    second_id = "e" * 40
    listing = (
        f"100644 blob {first_id}\ttests/fixtures/sample_campaigns/linden-pass/campaign.yaml\0"
        f"100644 blob {second_id}\ttests/fixtures/sample_campaigns/linden-pass/assets/pixel.bin\0"
    ).encode()

    def runner(_root, *arguments):
        if arguments[0] == "ls-tree":
            return SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
        object_id = arguments[-1]
        payload = b"fixture\n" if object_id == first_id else b"\x00\xff"
        return SimpleNamespace(returncode=0, stdout=payload, stderr=b"")

    proof = materialize_git_object_fixture(root, destination, runner=runner)
    assert proof["source"] == "git-object"
    assert proof["file_count"] == 2
    literal = f"\\\\?\\{destination}" if os.name == "nt" else os.fspath(destination)
    with open(os.path.join(literal, "campaign.yaml"), "rb") as stream:
        assert stream.read() == b"fixture\n"
    with open(os.path.join(literal, "assets", "pixel.bin"), "rb") as stream:
        assert stream.read() == b"\x00\xff"


@pytest.mark.parametrize(
    "suffix",
    (
        "..\\escape",
        "C:escape",
        "device/CON.txt",
        "trailing./file.txt",
        "trailing-space /file.txt",
        "nested//file.txt",
        "nested/../file.txt",
    ),
)
def test_git_object_fixture_refuses_noncanonical_cross_platform_paths(tmp_path: Path, suffix: str):
    root = tmp_path.resolve()
    destination = tmp_path / "must-not-exist"
    object_id = "f" * 40
    tracked = f"tests/fixtures/sample_campaigns/linden-pass/{suffix}"
    listing = f"100644 blob {object_id}\t{tracked}\0".encode()

    def runner(_root, *arguments):
        if arguments[0] == "ls-tree":
            return SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"payload", stderr=b"")

    with pytest.raises(ContractError, match="fixture"):
        materialize_git_object_fixture(root, destination, runner=runner)
    assert not destination.exists()


def test_fixture_digests_bind_tracked_path_topology(tmp_path: Path):
    root = tmp_path.resolve()
    object_id = "c" * 40
    prefix = "tests/fixtures/sample_campaigns/linden-pass"

    def text_runner(path):
        def runner(_root, *arguments):
            if arguments[0] == "ls-tree":
                return SimpleNamespace(
                    returncode=0,
                    stdout=f"100644 blob {object_id}\t{prefix}/{path}\0",
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        return runner

    first_proof = prove_git_object_fixture(root, runner=text_runner("one.yaml"))
    second_proof = prove_git_object_fixture(root, runner=text_runner("nested/one.yaml"))
    assert first_proof["fixture_digest"] != second_proof["fixture_digest"]

    def bytes_runner(path):
        listing = f"100644 blob {object_id}\t{prefix}/{path}\0".encode()

        def runner(_root, *arguments):
            if arguments[0] == "ls-tree":
                return SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
            return SimpleNamespace(returncode=0, stdout=b"same bytes", stderr=b"")

        return runner

    first_materialized = materialize_git_object_fixture(
        root,
        tmp_path / "first",
        runner=bytes_runner("one.yaml"),
    )
    second_materialized = materialize_git_object_fixture(
        root,
        tmp_path / "second",
        runner=bytes_runner("nested/one.yaml"),
    )
    assert (
        first_materialized["materialized_digest"]
        != second_materialized["materialized_digest"]
    )


def test_bounded_server_has_one_acceptor_exactly_four_workers_and_true_wsgi_flag():
    lock = threading.Lock()
    four_entered = threading.Event()
    release = threading.Event()
    active = 0
    high_water = 0
    multithread_values = []

    def app(environ, start_response):
        nonlocal active, high_water
        with lock:
            active += 1
            high_water = max(high_water, active)
            multithread_values.append(environ.get("wsgi.multithread"))
            if active == 4:
                four_entered.set()
        try:
            if not release.wait(timeout=5):
                raise AssertionError("deterministic worker gate timed out")
            start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", "2")])
            return [b"ok"]
        finally:
            with lock:
                active -= 1

    server = FourWorkerWSGIServer(app)
    server.start()
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            def request_status(_index):
                with urlopen(server.base_url, timeout=10) as response:
                    return response.status

            futures = [executor.submit(request_status, index) for index in range(8)]
            assert four_entered.wait(timeout=5)
            with lock:
                assert high_water == 4
            release.set()
            statuses = [future.result(timeout=10) for future in futures]
    finally:
        release.set()
        server.stop()
    assert statuses == [200] * 8
    assert high_water == 4
    assert multithread_values == [True] * 8
    assert server.acceptor_count == 1
    assert server.worker_count == 4


def test_process_memory_sampler_returns_strict_current_and_peak_bytes():
    memory = process_memory_snapshot()
    assert set(memory) == {"rss_bytes", "peak_rss_bytes"}
    assert isinstance(memory["rss_bytes"], int) and memory["rss_bytes"] > 0
    assert isinstance(memory["peak_rss_bytes"], int)
    assert memory["peak_rss_bytes"] >= memory["rss_bytes"]


def test_async_collector_closes_with_exact_ledger_before_artifact_work():
    source = inspect.getsource(AsyncBrowserCollector.collect_all)
    for collector_name in (
        "collect_direct_network_surfaces",
        "collect_stateful_reads",
        "collect_mutations",
        "collect_root_smoke",
        "collect_ordinary_pressure",
        "collect_overload_pressure",
    ):
        assert source.count(collector_name) == 1
    assert "validate_attempt_ledger(samples)" in source


def test_absolute_script_candidate_import_boundary_is_repo_first_and_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    benign_collection_root = tmp_path / "pytest-collection-root"
    benign_collection_root.mkdir()
    monkeypatch.syspath_prepend(os.fspath(benign_collection_root))
    assert Path(sys.path[0]).resolve(strict=True) == benign_collection_root.resolve(strict=True)

    assert_candidate_import_boundary()
    assert Path(sys.path[0]).resolve(strict=True) == SCRIPT_REPO_ROOT
    assert any(
        Path(entry).resolve(strict=False) == benign_collection_root.resolve(strict=True)
        for entry in sys.path[1:]
        if entry
    )

    outside_package = tmp_path / "player_wiki" / "__init__.py"
    outside_package.parent.mkdir()
    outside_package.write_text("", encoding="utf-8")
    with pytest.raises(ContractError, match="outside the exact candidate"):
        assert_candidate_import_boundary(
            finder=lambda _name: SimpleNamespace(origin=os.fspath(outside_package))
        )


def test_candidate_import_boundary_refuses_already_loaded_outside_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    outside_package = tmp_path / "player_wiki" / "__init__.py"
    outside_package.parent.mkdir()
    outside_package.write_text("", encoding="utf-8")
    outside_module = SimpleNamespace(
        __file__=os.fspath(outside_package),
        __spec__=SimpleNamespace(origin=os.fspath(outside_package)),
    )
    monkeypatch.setitem(sys.modules, "player_wiki", outside_module)

    with pytest.raises(ContractError, match="outside the exact candidate"):
        assert_candidate_import_boundary()


def test_environment_manifest_retains_sanitized_exact_runtime_identity(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements-dev.lock").write_text(
        "playwright==1.61.0\nwerkzeug==3.1.8\n",
        encoding="utf-8",
    )
    chromium = tmp_path / "chromium.exe"
    chromium.write_bytes(b"synthetic executable")
    browser = browser_environment_identity("1.61.0", "140.0.7339.16", chromium)
    manifest = environment_manifest(
        repo,
        browser,
        distributions=(
            ("Playwright", "1.61.0"),
            ("Werkzeug", "3.1.8"),
            ("pip", "25.0.1"),
        ),
        os_build="10.0.26100",
        architecture="AMD64",
        cpu_class="Family 6 Model 154 Stepping 3",
        memory_mib=32768,
    )
    assert set(manifest) == {
        "platform",
        "os_build_components",
        "architecture",
        "python_major",
        "python_minor",
        "python_micro",
        "interpreter_sha256",
        "development_lock_sha256",
        "installed_distribution_count",
        "installed_distribution_inventory_sha256",
        "locked_requirement_count",
        "locked_requirements_match",
        "logical_cpu_count",
        "cpu_class_sha256",
        "total_memory_mib",
        "server_acceptors",
        "server_workers",
        "live_diagnostics",
        "browser",
    }
    assert manifest["os_build_components"] == [10, 0, 26100]
    assert manifest["architecture"] == "x86_64"
    assert manifest["installed_distribution_count"] == 3
    assert manifest["locked_requirement_count"] == 2
    assert manifest["locked_requirements_match"] is True
    assert manifest["total_memory_mib"] == 32768
    assert manifest["browser"] == {
        "playwright_release_components": [1, 61, 0],
        "chromium_release_components": [140, 0, 7339, 16],
        "chromium_executable_sha256": hashlib.sha256(b"synthetic executable").hexdigest(),
    }
    assert privacy_findings(manifest) == ()
    assert "Family" not in repr(manifest)
    with pytest.raises(ContractError, match="do not match"):
        environment_manifest(
            repo,
            browser,
            distributions=(("Playwright", "1.60.0"), ("Werkzeug", "3.1.8")),
            os_build="10.0.26100",
            architecture="AMD64",
            cpu_class="test cpu class",
            memory_mib=1024,
        )


@pytest.mark.parametrize(
    "run_id",
    (
        "slice0b-baseline-20260229-abcdef12",
        "slice0b-baseline-20260811-ABCDEF12",
        "slice0b-baseline-20260811-abcdef1",
        "slice0b-baseline-20260811-abcdef12345678901",
        "baseline-20260811-abcdef12",
    ),
)
def test_run_id_refuses_nonanonymous_format_or_invalid_calendar_date(run_id):
    with pytest.raises(EvidenceRefusal):
        validate_run_id(run_id)


def test_run_id_accepts_valid_calendar_date_and_refuses_before_directory_creation(tmp_path: Path):
    valid = "slice0b-baseline-20240229-abcdef123456"
    assert validate_run_id(valid) == valid
    evidence = tmp_path / "repo" / EVIDENCE_RELATIVE_ROOT
    with pytest.raises(EvidenceRefusal, match="anonymous"):
        EvidenceEnvelope(tmp_path / "repo", evidence, "invalid")
    assert not evidence.exists()


def test_async_collector_owns_navigation_phases_and_dispatches_all_six(monkeypatch):
    for method_name in ("collect_direct_network_surfaces", "collect_root_smoke"):
        method = getattr(AsyncBrowserCollector, method_name)
        assert inspect.iscoroutinefunction(method)
        assert method.__qualname__.startswith("AsyncBrowserCollector.")

    phases = (
        "collect_direct_network_surfaces",
        "collect_stateful_reads",
        "collect_mutations",
        "collect_root_smoke",
        "collect_ordinary_pressure",
        "collect_overload_pressure",
    )
    calls = []
    collector = object.__new__(AsyncBrowserCollector)

    def phase_collector(method_name):
        async def collect_phase():
            calls.append(method_name)
            return [{"phase": method_name}]

        return collect_phase

    for method_name in phases:
        monkeypatch.setattr(collector, method_name, phase_collector(method_name))
    monkeypatch.setattr(
        character_measurement,
        "validate_attempt_ledger",
        lambda samples: tuple(samples),
    )

    samples = _asyncio().run(AsyncBrowserCollector.collect_all(collector))

    assert calls == list(phases)
    assert samples == [{"phase": method_name} for method_name in phases]


def test_ordinary_pressure_dispatches_exact_five_actor_round_mapping(monkeypatch):
    calls = []

    class FakePage:
        def __init__(self, actor):
            self.actor = actor

        async def close(self):
            return None

    class FakeContext:
        def __init__(self, actor):
            self.actor = actor

        async def new_page(self):
            return FakePage(self.actor)

    collector = object.__new__(AsyncBrowserCollector)
    collector._actor_contexts = {
        actor.key: FakeContext(actor.key)
        for actor in ACTORS
    }
    collector.live_intervals_ms = {}

    async def prepare(page, *, actor, surface):
        calls.append(("prepare", actor, surface, page.actor))
        return surface

    async def normal(page, attempt):
        calls.append(("normal", attempt.sample_index, attempt.actor, attempt.surface, page.actor))
        return {"attempt_id": attempt.attempt_id}

    async def fragment(page, attempt):
        calls.append(("fragment", attempt.sample_index, attempt.actor, attempt.surface, page.actor))
        return {"attempt_id": attempt.attempt_id}

    async def live(page, metric_view, attempt):
        calls.append(("live", attempt.sample_index, attempt.actor, attempt.surface, page.actor))
        assert metric_view == attempt.surface
        return {"attempt_id": attempt.attempt_id}

    monkeypatch.setattr(collector, "_prepare_live_sampler", prepare)
    monkeypatch.setattr(collector, "_ordinary_character_read", normal)
    monkeypatch.setattr(collector, "_ordinary_session_fragment_read", fragment)
    monkeypatch.setattr(collector, "_ordinary_live_read", live)

    samples = _asyncio().run(AsyncBrowserCollector.collect_ordinary_pressure(collector))

    assert len(samples) == 60
    assert [call[1:3] for call in calls if call[0] == "prepare"] == [
        ("observer_primary", "combat-live"),
        ("observer_secondary", "session-live"),
    ]
    measured_calls = [call for call in calls if call[0] != "prepare"]
    for round_index in range(1, 13):
        round_calls = [call for call in measured_calls if call[1] == round_index]
        assert {(call[0], call[2], call[3]) for call in round_calls} == {
            ("fragment", "dm", "session-character-fragment"),
            ("normal", "assigned_player", "normal-character"),
            ("normal", "unassigned_player", "normal-character"),
            ("live", "observer_primary", "combat-live"),
            ("live", "observer_secondary", "session-live"),
        }
        assert {call[2] for call in round_calls} == {
            "dm",
            "assigned_player",
            "unassigned_player",
            "observer_primary",
            "observer_secondary",
        }


def test_local_wrapper_routes_baseline_through_explicit_python_shortroot_and_lock():
    wrapper = (Path(__file__).resolve().parents[1] / "local.ps1").read_text(encoding="utf-8")
    assert '"character-read-baseline"' in wrapper.splitlines()[1]
    assert "PLAYER_WIKI_CHARACTER_READ_RUN_ID" in wrapper
    assert "PLAYER_WIKI_CHARACTER_READ_EVIDENCE_ROOT" in wrapper
    assert '& $PythonPath `' in wrapper
    assert '(Join-Path $projectRoot "scripts\\measure_character_read_performance.py")' in wrapper
    shortroot_block = wrapper.split("$shortRootActions = @(", 1)[1].split(")", 1)[0]
    assert '"character-read-baseline"' in shortroot_block
    assert (
        '$completeActions = @("character-read-baseline", "candidate-gate", "test", "check")'
        in wrapper
    )
    assert "Invoke-WithCompleteValidationLock" in wrapper
    assert "-RemoveOnSuccess:$RemoveShortRootOnSuccess" in wrapper


@pytest.mark.skipif(sys.platform != "win32", reason="local.ps1 is Windows-only")
@pytest.mark.windows_host
def test_local_wrapper_validates_character_evidence_root_with_windows_powershell(
    tmp_path: Path,
):
    powershell = shutil.which("powershell.exe")
    assert powershell is not None, "Windows PowerShell is required for this wrapper gate"
    wrapper = SCRIPT_REPO_ROOT / "local.ps1"
    base_environment = os.environ.copy()
    base_environment.pop("PLAYER_WIKI_SHORT_ROOT_ACTIVE", None)
    base_environment.pop("PLAYER_WIKI_VALIDATION_LOCK_HELD", None)
    base_environment["PLAYER_WIKI_CHARACTER_READ_RUN_ID"] = "invalid-run-id"

    def invoke(evidence_root: str) -> subprocess.CompletedProcess[str]:
        environment = dict(base_environment)
        environment["PLAYER_WIKI_CHARACTER_READ_EVIDENCE_ROOT"] = evidence_root
        return subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                os.fspath(wrapper),
                "-Action",
                "character-read-baseline",
                "-PythonPath",
                sys.executable,
            ],
            cwd=SCRIPT_REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    invalid_roots = (
        "relative\\character-read-evidence",
        "C:character-read-evidence",
        "\\character-read-evidence",
        "Env:\\character-read-evidence",
        "Microsoft.PowerShell.Core\\FileSystem::C:\\character-read-evidence",
        r"\\?\C:\character-read-evidence",
        r"\\.\C:\character-read-evidence",
        r"\\measurement-host.invalid",
    )
    for evidence_root in invalid_roots:
        refused = invoke(evidence_root)
        output = refused.stdout + refused.stderr
        assert refused.returncode != 0
        assert "PLAYER_WIKI_CHARACTER_READ_EVIDENCE_ROOT must be an absolute path." in output

    drive_root = tmp_path / "drive-absolute-evidence"
    accepted_drive = invoke(os.fspath(drive_root))
    drive_output = accepted_drive.stdout + accepted_drive.stderr
    assert accepted_drive.returncode != 0
    assert "must be an absolute path" not in drive_output
    assert "Character-read baseline refused by its fixed contract." in drive_output
    assert "Character-read baseline harness failed." in drive_output
    assert not drive_root.exists()

    accepted_unc = invoke(r"\\measurement-host.invalid\sanitized-share\evidence")
    unc_output = accepted_unc.stdout + accepted_unc.stderr
    assert accepted_unc.returncode != 0
    assert "must be an absolute path" not in unc_output
    assert "Character-read baseline refused by its fixed contract." in unc_output
    assert "Character-read baseline harness failed." in unc_output


def test_acceptance_contract_pins_formulas_without_claiming_optimization():
    contract = acceptance_contract()
    assert contract["relative_session_server_p95_reduction_percent"] == 60
    assert contract["relative_normal_server_p95_reduction_percent"] == 50
    assert contract["maximum_live_regression_percent"] == 15
    assert contract["cold_selected_section_p95_ms"] == 2000
    assert contract["warm_selected_section_network_p95_ms"] == 750
    assert contract["cached_apply_p95_ms"] == 100
    assert contract["optimization_success_claimed"] is False


def test_baseline_freeze_requires_exact_schedule_zero_errors_and_clean_scan():
    posts = [attempt for attempt in ATTEMPT_SCHEDULE if attempt.scenario == "session_mutation_post"]
    samples = [
        _sample(
            attempt,
            status_code=302 if attempt in posts else attempt.expected_statuses[0],
        )
        for attempt in ATTEMPT_SCHEDULE
    ]
    result = evaluate_baseline_freeze(samples, safety_findings=[])
    assert result["baseline_frozen"] is True
    assert result["optimization_success_claimed"] is False
    with pytest.raises(ContractError, match="attempt ledger differs"):
        evaluate_baseline_freeze(samples[:-1], safety_findings=[])
    assert evaluate_baseline_freeze(samples, safety_findings=[{"code": "email", "location": "root"}])["baseline_frozen"] is False


def _evidence_git_result(repo):
    def git_result(_root, *arguments):
        stdout = (
            f"worktree {repo}\n"
            if arguments[:3] == ("worktree", "list", "--porcelain")
            else ""
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return git_result


def _write_pre_manifest_artifacts(envelope):
    envelope.write_json("samples.json", {"schema": "safe", "attempt_count": 1})
    envelope.write_summary("# Safe baseline\n\nAttempt count: 1.\n")
    envelope.write_json("acceptance.json", {"baseline_frozen": True})
    envelope.write_json("safety-scan.json", {"clean": True, "finding_count": 0})


def _exact_manifest(envelope, run_id):
    return {
        "schema": SCHEMA,
        "run_id": run_id,
        "artifact_count": len(ARTIFACT_ORDER),
        "manifest_written_last": True,
        "artifact_sha256_scope": list(PRE_MANIFEST_ARTIFACTS),
        "artifact_sha256": {
            name: character_measurement._sha256_file(envelope.staging / name)
            for name in PRE_MANIFEST_ARTIFACTS
        },
    }


def test_no_overwrite_envelope_requires_exact_manifest_and_detects_staged_tamper(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    evidence = repo / ".local" / "evidence" / "character-read-performance" / "slice-0"
    evidence.mkdir(parents=True)
    monkeypatch.setattr(
        "scripts.measure_character_read_performance._run_git",
        _evidence_git_result(repo),
    )
    run_id = "slice0b-baseline-20260811-abcdef12"
    envelope = EvidenceEnvelope(repo, evidence, run_id)
    _write_pre_manifest_artifacts(envelope)
    valid_manifest = _exact_manifest(envelope, run_id)
    with pytest.raises(EvidenceRefusal, match="manifest-last"):
        envelope.seal({**valid_manifest, "manifest_written_last": False})
    published = envelope.seal(valid_manifest)
    literal = f"\\\\?\\{published}" if os.name == "nt" else os.fspath(published)
    assert sorted(os.listdir(literal)) == sorted(ARTIFACT_ORDER)
    assert os.path.exists(os.path.join(literal, "manifest.json"))
    with pytest.raises(EvidenceRefusal, match="already exists"):
        EvidenceEnvelope(repo, evidence, run_id)

    tamper_run_id = "slice0b-baseline-20260811-fedcba98"
    tampered = EvidenceEnvelope(repo, evidence, tamper_run_id)
    _write_pre_manifest_artifacts(tampered)
    tampered_manifest = _exact_manifest(tampered, tamper_run_id)
    with open(
        character_measurement._filesystem_path(tampered.staging / "samples.json"),
        "ab",
    ) as stream:
        stream.write(b"tamper")
    with pytest.raises(EvidenceRefusal, match="hashes differ"):
        tampered.seal(tampered_manifest)


def test_envelope_refuses_wrong_write_order_and_unapproved_root(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    evidence = repo / ".local" / "evidence" / "character-read-performance" / "slice-0"
    evidence.mkdir(parents=True)
    monkeypatch.setattr(
        "scripts.measure_character_read_performance._run_git",
        _evidence_git_result(repo),
    )
    envelope = EvidenceEnvelope(
        repo,
        evidence,
        "slice0b-baseline-20260811-00000002",
    )
    with pytest.raises(EvidenceRefusal, match="fixed order"):
        envelope.write_summary("safe")
    wrong = repo / ".local" / "wrong"
    wrong.mkdir(parents=True)
    with pytest.raises(EvidenceRefusal, match="authorized"):
        EvidenceEnvelope(
            repo,
            wrong,
            "slice0b-baseline-20260811-00000003",
        )


def test_envelope_refuses_symlink_or_reparse_in_existing_suffix(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    local = repo / ".local"
    local.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence_link = local / "evidence"
    link_kind = "symlink"
    try:
        evidence_link.symlink_to(outside, target_is_directory=True)
    except OSError as symlink_error:
        if os.name != "nt":
            pytest.skip(f"cannot create a test directory symlink: {symlink_error}")
        resolved_temp = tmp_path.resolve(strict=True)
        assert local.resolve(strict=True).is_relative_to(resolved_temp)
        assert outside.resolve(strict=True).is_relative_to(resolved_temp)
        junction = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                os.fspath(evidence_link),
                os.fspath(outside),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if junction.returncode != 0 or not os.path.lexists(evidence_link):
            pytest.skip(
                "Windows cannot create a test symlink or junction "
                f"(symlink={symlink_error.winerror}, junction={junction.returncode})"
            )
        link_kind = "junction"
    evidence = evidence_link / "character-read-performance" / "slice-0"
    monkeypatch.setattr(
        "scripts.measure_character_read_performance._run_git",
        _evidence_git_result(repo),
    )
    try:
        with pytest.raises(EvidenceRefusal, match="reparse"):
            EvidenceEnvelope(
                repo,
                evidence,
                "slice0b-baseline-20260811-00000004",
            )
        assert not (outside / "character-read-performance").exists()
    finally:
        if os.path.lexists(evidence_link):
            if link_kind == "symlink":
                evidence_link.unlink()
            else:
                os.rmdir(evidence_link)


@pytest.mark.skipif(
    os.environ.get("PLAYER_WIKI_CHARACTER_READ_BROWSER_SMOKE") != "1",
    reason="set PLAYER_WIKI_CHARACTER_READ_BROWSER_SMOKE=1 for the creditable browser gate",
)
def test_real_browser_mounted_mutation_ordinary_round_and_overload_smoke(
    monkeypatch: pytest.MonkeyPatch,
):
    from player_wiki.config import Config

    for field_name in (
        "APP_ENV",
        "TESTING",
        "DEBUG",
        "CAMPAIGNS_DIR",
        "DB_PATH",
        "SECRET_KEY",
        "LIVE_DIAGNOSTICS",
        "REQUEST_TRAIL_ENABLED",
        "RELOAD_CONTENT",
        "CONTENT_SCAN_INTERVAL_SECONDS",
        "CHARACTER_READ_MAX_CONCURRENT_RENDERS",
    ):
        monkeypatch.setattr(
            Config,
            field_name,
            getattr(Config, field_name, None),
            raising=False,
        )

    async def exercise(runtime_root: Path):
        bootstrap = character_measurement.bootstrap_runtime_app(
            SCRIPT_REPO_ROOT,
            runtime_root,
        )
        gate = character_measurement.install_harness_render_gate(bootstrap.app)
        server = FourWorkerWSGIServer(bootstrap.app)
        server.start()
        try:
            async with AsyncBrowserCollector(server.base_url, bootstrap, gate) as collector:
                mutations = await collector.collect_mutations()
                cached_apply_attempt = next(
                    attempt
                    for attempt in ATTEMPT_SCHEDULE
                    if attempt.scenario == "session_section_cached_apply"
                    and attempt.section == "resources"
                )
                cached_apply = await collector.collect_session_cached_apply(
                    cached_apply_attempt
                )

                round_attempts = [
                    attempt
                    for attempt in ATTEMPT_SCHEDULE
                    if attempt.pressure_group == "ordinary" and attempt.sample_index == 1
                ]
                pages = {
                    actor.key: await collector._actor_contexts[actor.key].new_page()
                    for actor in ACTORS
                }
                try:
                    metric_views = {}
                    for attempt in round_attempts:
                        if attempt.zero_contract == "unchanged-live":
                            metric_views[attempt.actor] = await collector._prepare_live_sampler(
                                pages[attempt.actor],
                                actor=attempt.actor,
                                surface=attempt.surface,
                            )
                    operations = []
                    for attempt in round_attempts:
                        if attempt.surface == "normal-character":
                            operations.append(
                                collector._ordinary_character_read(
                                    pages[attempt.actor],
                                    attempt,
                                )
                            )
                        elif attempt.surface == "session-character-fragment":
                            operations.append(
                                collector._ordinary_session_fragment_read(
                                    pages[attempt.actor],
                                    attempt,
                                )
                            )
                        else:
                            operations.append(
                                collector._ordinary_live_read(
                                    pages[attempt.actor],
                                    metric_views[attempt.actor],
                                    attempt,
                                )
                            )
                    ordinary = await _asyncio().gather(*operations)
                finally:
                    for page in pages.values():
                        await page.close()

                ready_precondition = await collector._actor_contexts[
                    "observer_primary"
                ].request.get(f"{server.base_url}/readyz")
                assert ready_precondition.status == 200
                overload = await collector.collect_overload_pressure()
                return (
                    mutations,
                    cached_apply,
                    ordinary,
                    overload,
                    dict(collector.browser_identity),
                )
        finally:
            gate.release()
            server.stop()

    with tempfile.TemporaryDirectory(
        prefix="character-read-smoke-",
    ) as temporary_root:
        mutations, cached_apply, ordinary, overload, browser_identity = _asyncio().run(
            exercise(Path(temporary_root))
        )

    assert len(mutations) == 12
    assert cached_apply["status_code"] == 200
    assert cached_apply["network_request_count"] == 0
    assert len(ordinary) == 5
    assert len(overload) == 15
    assert len(browser_identity["playwright_release_components"]) >= 2
    assert len(browser_identity["chromium_release_components"]) >= 2
    actual_environment = environment_manifest(SCRIPT_REPO_ROOT, browser_identity)
    assert actual_environment["locked_requirements_match"] is True
    assert actual_environment["server_workers"] == 4
