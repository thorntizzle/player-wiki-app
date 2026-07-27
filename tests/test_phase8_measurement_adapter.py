from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import types
from uuid import uuid4

import pytest

from tests.helpers import phase8_measurement_envelope as measurement_envelope
from tests.helpers.phase8_measurement_adapter import (
    ADAPTER_SCHEMA,
    ContractError,
    IMPORTED_PHASE7_EVIDENCE,
    LOCK_SHA256,
    PHASE4_IDENTITY,
    PHASE8_IDENTITY,
    PHASE8_HARNESS_BLOB,
    SAMPLE_COUNTS,
    SAMPLER_COLLECTION_POLICY,
    SURFACES,
    build_candidate_artifact,
    build_measurement_manifest,
    canonical_provenance_sha256,
    canonical_json_sha256,
    CANONICAL_DIAGNOSTICS,
    CANONICAL_LOCAL_SETTINGS,
    CANONICAL_SCHEMA,
    _collect_with_playwright,
    fixture_manifest_proof,
    collect_candidate,
    evaluate_pair,
    main,
    parse_server_timing,
    write_deterministic_bundles,
)
from tests.helpers.phase8_measurement_envelope import (
    CAMPAIGN_SLUG,
    COMBAT_CHARACTER_SLUG,
    PHASE8_ENVELOPE_IDENTITY,
    PHASE8_ENVELOPE_SUPPORT_PATHS,
    create_synthetic_measurement_envelope,
)


def _manifest(candidate: str) -> dict[str, object]:
    identity = (
        PHASE4_IDENTITY
        if candidate == "phase4"
        else {
            **PHASE8_IDENTITY,
        }
    )
    return {
        "adapter_schema": ADAPTER_SCHEMA,
        "candidate": {"name": candidate, **identity},
        "fixture_sha256": "BEDFA24251CBE9BEE44EDC0771B223E34037028E081ADCA0CABB43531897D8F1",
        **canonical_provenance_sha256(),
        "runtime": {"python": "3.12.12", "development_lock_sha256": LOCK_SHA256},
        "combat_character": {"slug": "arden-march", "assigned": True},
        "actors": {
            "player": {"present": True, "principal": "player-fixture"},
            "manager": {"present": True, "principal": "manager-fixture"},
        },
        "surface_manifest": [surface.__dict__ for surface in SURFACES],
        "console_error_allowlist": [r"^known diagnostics noise$"],
    }


def _sample(*, changed: bool, request: float = 10.0, db: float = 2.0, render: float = 0.0, apply: float = 0.0, payload: float = 100.0) -> dict[str, object]:
    return {
        "requestMs": request,
        "applyMs": apply,
        "payloadBytes": payload,
        "requestTimeMs": request / 2,
        "serverTiming": f"state-check;dur=0.25, db;dur={db:.2f}, render;dur={render:.2f}, total;dur={request / 2:.2f}",
        "changed": changed,
        "phase_specific_raw_key": "preserved without normalization",
    }


def _raw() -> dict[str, object]:
    surfaces: dict[str, object] = {}
    for surface in SURFACES:
        surfaces[surface.name] = {
            "dataset": {"liveActiveIntervalMs": "500", "liveIdleIntervalMs": "2000"},
            "scenarios": {
                "warmup": [_sample(changed=False)],
                "cold": [_sample(changed=True, request=10, db=2, render=1, apply=2, payload=1000) for _ in range(8)],
                "steady": [_sample(changed=False, request=1, db=0.2, render=0, apply=0, payload=100) for _ in range(12)],
                "forced_apply": [_sample(changed=True, request=10, db=2, render=1, apply=2, payload=1000) for _ in range(6)],
            },
            "errors": [],
        }
    return {"surfaces": surfaces}


def _incomplete_phase8_raw() -> dict[str, object]:
    raw = _raw()
    status = raw["surfaces"]["dm_combat_status"]
    status["scenarios"]["warmup"] = []
    status["errors"] = [
        {
            "kind": "sampler_exception",
            "message": "async read has no ticket at C:\\private\\phase8 password=not-for-bundle",
        }
    ]
    return raw


def _artifact(candidate: str) -> dict[str, object]:
    return build_candidate_artifact(_manifest(candidate), _raw())


def _phase4_measurement_module() -> types.ModuleType:
    result = subprocess.run(
        ["git", "show", "b80af7c7b441bb2fcecc763bf6ea4a73f9d85365:scripts/measure_live_latency.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    module = types.ModuleType("phase4_measure_live_latency_characterization")
    sys.modules[module.__name__] = module
    exec(compile(result.stdout, "phase4_measure_live_latency.py", "exec"), module.__dict__)
    return module


class _FakeResponse:
    status = 200


class _FakeLocator:
    def __init__(self, page: "_FakePage"):
        self.page = page

    def fill(self, value: str) -> None:
        self.page.filled.append(value)

    def click(self) -> None:
        self.page.clicked += 1
        self.page.url = "http://127.0.0.1:5000/campaign-picker"

    def evaluate(self, _script: str) -> dict[str, str]:
        return {"liveDiagnosticsEnabled": "1", "liveActiveIntervalMs": "500", "liveIdleIntervalMs": "2000"}


class _FakePage:
    def __init__(self):
        self.url = ""
        self.events: dict[str, object] = {}
        self.filled: list[str] = []
        self.clicked = 0
        self.sampler_calls: list[dict[str, object]] = []
        self.waits: list[int] = []

    def on(self, name: str, callback: object) -> None:
        self.events[name] = callback

    def goto(self, url: str, **_kwargs: object) -> _FakeResponse:
        self.url = url
        return _FakeResponse()

    def locator(self, _selector: str) -> _FakeLocator:
        return _FakeLocator(self)

    def wait_for_load_state(self, _state: str) -> None:
        return None

    def wait_for_selector(self, _selector: str, **_kwargs: object) -> None:
        return None

    def wait_for_function(self, _script: str, **_kwargs: object) -> None:
        return None

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.waits.append(timeout_ms)

    def evaluate(self, _script: str, arguments: dict[str, object]) -> dict[str, object]:
        self.sampler_calls.append(arguments)
        return _sample(changed=bool(arguments["forceApply"]), render=1 if arguments["forceApply"] else 0)


class _ContextLocator:
    def __init__(self, page: "_ContextPage"):
        self.page = page

    def fill(self, value: str) -> None:
        self.page.filled.append(value)

    def click(self) -> None:
        email = self.page.filled[0]
        self.page.context.login_emails.append(email)
        if self.page.context.fail_sign_in:
            self.page.url = "http://127.0.0.1:5000/sign-in"
            return
        self.page.context.cookies.append(f"session-for:{email}")
        self.page.url = "http://127.0.0.1:5000/campaign-picker"

    def evaluate(self, _script: str) -> dict[str, str]:
        return {"liveDiagnosticsEnabled": "1", "liveActiveIntervalMs": "500", "liveIdleIntervalMs": "2000"}


class _ContextPage(_FakePage):
    def __init__(self, context: "_Context"):
        super().__init__()
        self.context = context
        self.closed = False

    def locator(self, _selector: str) -> _ContextLocator:
        return _ContextLocator(self)

    def close(self) -> None:
        self.closed = True


class _Context:
    def __init__(self, *, fail_sign_in: bool = False):
        self.fail_sign_in = fail_sign_in
        self.cookies: list[str] = []
        self.login_emails: list[str] = []
        self.pages: list[_ContextPage] = []
        self.closed = False

    def new_page(self) -> _ContextPage:
        page = _ContextPage(self)
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


class _ContextBrowser:
    def __init__(self, *, failed_context_index: int | None = None):
        self.failed_context_index = failed_context_index
        self.contexts: list[_Context] = []
        self.closed = False

    def new_context(self) -> _Context:
        context = _Context(fail_sign_in=len(self.contexts) == self.failed_context_index)
        self.contexts.append(context)
        return context

    def close(self) -> None:
        self.closed = True


class _ContextChromium:
    def __init__(self, browser: _ContextBrowser):
        self.browser = browser
        self.launches: list[bool] = []

    def launch(self, *, headless: bool) -> _ContextBrowser:
        self.launches.append(headless)
        return self.browser


class _ContextPlaywright:
    def __init__(self, browser: _ContextBrowser):
        self.chromium = _ContextChromium(browser)


class _ContextPlaywrightManager:
    def __init__(self, browser: _ContextBrowser):
        self.playwright = _ContextPlaywright(browser)
        self.exited = False

    def __enter__(self) -> _ContextPlaywright:
        return self.playwright

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.exited = True


def _install_context_playwright(monkeypatch: pytest.MonkeyPatch, browser: _ContextBrowser) -> _ContextPlaywrightManager:
    manager = _ContextPlaywrightManager(browser)
    playwright_module = types.ModuleType("playwright")
    sync_api_module = types.ModuleType("playwright.sync_api")
    sync_api_module.sync_playwright = lambda: manager
    monkeypatch.setitem(sys.modules, "playwright", playwright_module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api_module)
    return manager


class _DmStatusNoTicketPage(_FakePage):
    def evaluate(self, script: str, arguments: dict[str, object]) -> dict[str, object]:
        if self.url.endswith("/combat/dm") and arguments["scenarioName"] == "warmup":
            raise RuntimeError("async read has no ticket at C:\\private\\phase8 password=not-for-bundle")
        return super().evaluate(script, arguments)


class _TransientPhase8SamplerPage(_FakePage):
    def __init__(self, transient_attempts: int = 2):
        super().__init__()
        self.transient_attempts = transient_attempts

    def evaluate(self, script: str, arguments: dict[str, object]) -> dict[str, object] | None:
        if (
            self.url.endswith("/combat/dm")
            and arguments["scenarioName"] == "warmup"
            and self.transient_attempts > 0
        ):
            self.transient_attempts -= 1
            self.sampler_calls.append(arguments)
            return None
        return super().evaluate(script, arguments)


class _ExhaustedPhase8SamplerPage(_FakePage):
    def evaluate(self, script: str, arguments: dict[str, object]) -> dict[str, object] | None:
        if self.url.endswith("/combat/dm") and arguments["scenarioName"] == "warmup":
            self.sampler_calls.append(arguments)
            return None
        return super().evaluate(script, arguments)


def test_manifest_pins_phase4_and_frozen_phase8_identities():
    assert PHASE4_IDENTITY == {
        "commit": "b80af7c7b441bb2fcecc763bf6ea4a73f9d85365",
        "tree": "30dc769f0f8d40b1f89307459cf2700541815c02",
        "harness_blob": "09340d98d72f99397c825489ea205b41dd6b3bba",
    }
    assert PHASE8_HARNESS_BLOB == "1d79c678a2c1f06a172eda9f6269c31517c36cec"
    assert PHASE8_IDENTITY == {
        "commit": "3fdb48c9bed822719a2c71c8463c7e52474cdd2d",
        "tree": "ea29374fdf895bd5d24bf3145872126e0b6fbc6f",
        "harness_blob": "1d79c678a2c1f06a172eda9f6269c31517c36cec",
    }
    assert SAMPLE_COUNTS == {"warmup": 1, "cold": 8, "steady": 12, "forced_apply": 6}
    assert [(surface.name, surface.actor) for surface in SURFACES] == [
        ("player_session", "player"),
        ("player_combat", "player"),
        ("dm_session_tools", "manager"),
        ("dm_combat_status", "manager"),
        ("dm_combat_controls", "manager"),
    ]
    assert IMPORTED_PHASE7_EVIDENCE["lifecycle"] == {
        "sha256": "386061832D7FCB978A30CCCD0C3B8EFCC8E07B68D397868885C1E132AED34701",
        "bytes": 159219,
    }
    assert IMPORTED_PHASE7_EVIDENCE["publishing_systems_brief"] == {
        "sha256": "C7768ACC7B3458AEF355C50A3FE6254EC1C80D0BE580A2DD939D6AE74BD9E633",
        "bytes": 29442,
    }
    root = Path(__file__).resolve().parents[1]
    assert build_measurement_manifest(
        "phase4",
        candidate_root=root,
        player_principal="phase8-player@example.test",
        manager_principal="phase8-manager@example.test",
    )["candidate"] == {"name": "phase4", **PHASE4_IDENTITY}
    assert build_measurement_manifest(
        "phase8",
        candidate_root=root,
        player_principal="phase8-player@example.test",
        manager_principal="phase8-manager@example.test",
    )["candidate"] == {"name": "phase8", **PHASE8_IDENTITY}


def test_synthetic_envelope_pins_accepted_assembled_phase8_runtime():
    assert PHASE8_ENVELOPE_IDENTITY == {
        "commit": "85bbd375362500b1b8cea961a82377b4e1ee6fff",
        "tree": "e3562804dd16842e159ea3f9d7a695b2167e9e7c",
        "harness_blob": PHASE8_IDENTITY["harness_blob"],
    }
    assert PHASE8_ENVELOPE_SUPPORT_PATHS == frozenset(
        {
            "tests/helpers/phase8_measurement_envelope.py",
            "tests/test_phase8_measurement_adapter.py",
        }
    )


def test_sampler_collection_policy_is_mirrored_from_the_committed_phase4_and_phase8_harnesses():
    phase4_source = subprocess.run(
        ["git", "show", f"{PHASE4_IDENTITY['commit']}:scripts/measure_live_latency.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    phase8_source = subprocess.run(
        ["git", "show", f"{PHASE8_IDENTITY['commit']}:scripts/measure_live_latency.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    phase4_runner = phase4_source.split("def run_surface_samples", 1)[1].split("def collect_surface_report", 1)[0]
    phase8_runner = phase8_source.split("def run_surface_samples", 1)[1].split("def collect_surface_report", 1)[0]

    assert SAMPLER_COLLECTION_POLICY == {
        "phase4": {"attempts": 1, "retry_wait_ms": None, "accepted_sample_wait_ms": 100},
        "phase8": {"attempts": 50, "retry_wait_ms": 50, "accepted_sample_wait_ms": 100},
    }
    assert phase4_runner.count("result = page.evaluate(") == 1
    assert "for _attempt in range(50):" not in phase4_runner
    assert "page.wait_for_timeout(50)" not in phase4_runner
    assert phase4_runner.count("page.wait_for_timeout(100)") == 1
    assert phase8_runner.count("result = page.evaluate(") == 1
    assert "for _attempt in range(50):" in phase8_runner
    assert "page.wait_for_timeout(50)" in phase8_runner
    assert phase8_runner.count("page.wait_for_timeout(100)") == 1


def test_source_fixture_and_bootstrap_blobs_are_phase4_phase8_equal():
    root = Path(__file__).resolve().parents[1]
    phase4_fixture = fixture_manifest_proof(root, PHASE4_IDENTITY["commit"])
    phase8_fixture = fixture_manifest_proof(root, PHASE8_IDENTITY["commit"])

    assert phase4_fixture == phase8_fixture == {
        "bytes": 5004,
        "sha256": "BEDFA24251CBE9BEE44EDC0771B223E34037028E081ADCA0CABB43531897D8F1",
    }
    bootstrap_paths = (
        "player_wiki/auth_store.py",
        "player_wiki/campaign_combat_service.py",
        "player_wiki/db.py",
        "player_wiki/migrations.py",
        "player_wiki/runtime_app.py",
    )
    for path in bootstrap_paths:
        phase4 = subprocess.run(
            ["git", "rev-parse", f"{PHASE4_IDENTITY['commit']}:{path}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        phase8 = subprocess.run(
            ["git", "rev-parse", f"{PHASE8_IDENTITY['commit']}:{path}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert phase4 == phase8


def test_manifest_provenance_is_canonical_and_rejects_tampering():
    expected = canonical_provenance_sha256()
    assert canonical_json_sha256(CANONICAL_LOCAL_SETTINGS) == expected["local_settings_sha256"]
    assert canonical_json_sha256(CANONICAL_DIAGNOSTICS) == expected["diagnostics_sha256"]
    assert canonical_json_sha256(CANONICAL_SCHEMA) == expected["schema_sha256"]
    manifest = _manifest("phase8")
    manifest["candidate"] = {**manifest["candidate"], "tree": "0" * 40}
    with pytest.raises(ContractError, match="frozen candidate"):
        build_candidate_artifact(manifest, _raw())
    manifest = _manifest("phase4")
    manifest["diagnostics_sha256"] = "0" * 64
    with pytest.raises(ContractError, match="canonical source-proven map"):
        build_candidate_artifact(manifest, _raw())


def test_artifact_and_compare_bundles_emit_stable_json_and_markdown(tmp_path):
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    hashes = write_deterministic_bundles(tmp_path, phase4, phase8)
    first = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}
    second_hashes = write_deterministic_bundles(tmp_path, phase4, phase8)
    second = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}

    assert hashes == second_hashes
    assert first == second
    assert sorted(first) == [
        "comparison.json",
        "comparison.md",
        "phase4.raw.json",
        "phase4.raw.md",
        "phase8.raw.json",
        "phase8.raw.md",
    ]
    comparison = json.loads(first["comparison.json"])
    assert comparison["source_sha256"] == {
        "phase4.raw.json": hashes["source_sha256"]["phase4.raw.json"],
        "phase8.raw.json": hashes["source_sha256"]["phase8.raw.json"],
    }
    assert comparison["output_sha256"]["phase4.raw.md"] == hashes["output_sha256"]["phase4.raw.md"]
    rendered = b"".join(first.values()).decode("utf-8")
    assert "C:\\" not in rendered
    assert "password" not in rendered.lower()
    assert "timestamp" not in rendered.lower()

    phase4_path = tmp_path / "source-phase4.json"
    phase8_path = tmp_path / "source-phase8.json"
    cli_output = tmp_path / "cli-bundle"
    phase4_path.write_bytes(json.dumps(phase4).encode("utf-8"))
    phase8_path.write_bytes(json.dumps(phase8).encode("utf-8"))
    assert main([
        "bundle",
        "--phase4",
        str(phase4_path),
        "--phase8",
        str(phase8_path),
        "--output-dir",
        str(cli_output),
    ]) == 0
    assert sorted(path.name for path in cli_output.iterdir()) == sorted(first)


def test_synthetic_envelope_is_ignored_source_derived_and_seeds_distinct_actors_and_arden():
    root = Path(__file__).resolve().parents[1]
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{PHASE8_ENVELOPE_IDENTITY['commit']}..HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert changed == sorted(PHASE8_ENVELOPE_SUPPORT_PATHS)
    frozen_fixture = fixture_manifest_proof(root, PHASE8_IDENTITY["commit"])
    accepted_fixture = measurement_envelope._accepted_phase8_fixture_proof(
        root,
        PHASE8_ENVELOPE_IDENTITY["commit"],
    )
    assert accepted_fixture == frozen_fixture == {
        "bytes": 5004,
        "sha256": "BEDFA24251CBE9BEE44EDC0771B223E34037028E081ADCA0CABB43531897D8F1",
    }
    envelope = create_synthetic_measurement_envelope(
        root,
        candidate_name="phase8",
        token=f"adapter-envelope-{uuid4().hex}",
    )

    assert envelope.root.parent.parent == root / ".local"
    ignored = subprocess.run(
        [
            "git",
            "check-ignore",
            "--quiet",
            "--no-index",
            str(envelope.root.relative_to(root)),
        ],
        check=False,
        capture_output=True,
    )
    assert ignored.returncode == 0
    assert (envelope.campaigns_dir / CAMPAIGN_SLUG / "characters" / COMBAT_CHARACTER_SLUG / "definition.yaml").is_file()
    metadata = json.loads(envelope.metadata_path.read_text(encoding="utf-8"))
    assert metadata["candidate"] == {"name": "phase8", **PHASE8_ENVELOPE_IDENTITY}
    assert metadata["fixture"] == accepted_fixture
    assert metadata["combat_character"] == {"assigned": True, "slug": "arden-march", "turn_value": 18}
    assert metadata["principals"]["player"]["email"] != metadata["principals"]["manager"]["email"]
    persisted = b"".join(path.read_bytes() for path in envelope.root.rglob("*") if path.is_file())
    assert envelope.credentials["player"][1].encode("utf-8") not in persisted
    assert envelope.credentials["manager"][1].encode("utf-8") not in persisted

    connection = sqlite3.connect(envelope.database_path)
    try:
        memberships = connection.execute(
            "SELECT account.email, membership.role, membership.status "
            "FROM campaign_memberships AS membership JOIN users AS account ON account.id = membership.user_id "
            "WHERE membership.campaign_slug = ? ORDER BY account.email",
            (CAMPAIGN_SLUG,),
        ).fetchall()
        assignment = connection.execute(
            "SELECT assignment.character_slug, account.email FROM character_assignments AS assignment "
            "JOIN users AS account ON account.id = assignment.user_id "
            "WHERE assignment.campaign_slug = ? AND assignment.character_slug = ?",
            (CAMPAIGN_SLUG, COMBAT_CHARACTER_SLUG),
        ).fetchone()
        combatant = connection.execute(
            "SELECT combatant_type, character_slug, turn_value FROM campaign_combatants "
            "WHERE campaign_slug = ? AND character_slug = ?",
            (CAMPAIGN_SLUG, COMBAT_CHARACTER_SLUG),
        ).fetchone()
    finally:
        connection.close()
    assert memberships == [
        ("phase8-manager@example.test", "dm", "active"),
        ("phase8-player@example.test", "player", "active"),
    ]
    assert assignment == ("arden-march", "phase8-player@example.test")
    assert combatant == ("player_character", "arden-march", 18)


def test_synthetic_envelope_rejects_unapproved_destination_or_identity(tmp_path):
    with pytest.raises(ContractError, match="Git root"):
        create_synthetic_measurement_envelope(tmp_path, candidate_name="phase8", token="invalid-root-123")
    with pytest.raises(ContractError, match="limited to the pinned phase4 or phase8 identities"):
        create_synthetic_measurement_envelope(
            Path(__file__).resolve().parents[1],
            candidate_name="unsupported",
            token=f"unsupported-{uuid4().hex}",
        )
    with pytest.raises(ContractError, match="pinned candidate"):
        create_synthetic_measurement_envelope(
            Path(__file__).resolve().parents[1],
            candidate_name="phase4",
            token=f"phase4-mismatch-{uuid4().hex}",
        )
    with pytest.raises(ContractError, match="token"):
        create_synthetic_measurement_envelope(
            Path(__file__).resolve().parents[1],
            candidate_name="phase8",
            token="../escape",
        )


@pytest.mark.parametrize("unlisted_path", ["player_wiki/app.py", "tests/test_unlisted_support.py"])
def test_synthetic_envelope_rejects_unlisted_descendant_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, unlisted_path: str
):
    head = "f" * 40
    tree = "e" * 40

    def fake_git(root: Path, *args: str, text: bool = True) -> str:
        assert root == tmp_path
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args == ("rev-parse", "HEAD"):
            return head
        if args == ("rev-parse", "HEAD^{tree}"):
            return tree
        if args == ("diff", "--name-only", f"{PHASE8_ENVELOPE_IDENTITY['commit']}..HEAD"):
            return f"{unlisted_path}\n"
        raise AssertionError(args)

    monkeypatch.setattr(measurement_envelope, "_git", fake_git)
    monkeypatch.setattr(
        measurement_envelope.subprocess,
        "run",
        lambda *_args, **_kwargs: types.SimpleNamespace(returncode=0),
    )

    with pytest.raises(ContractError, match="support boundary"):
        measurement_envelope._approved_root(tmp_path, "phase8")


def test_adapter_preserves_candidate_raw_envelope_and_emits_only_common_core():
    raw = _raw()
    artifact = build_candidate_artifact(_manifest("phase4"), raw)

    assert artifact["candidate_specific_raw"] == raw
    core_surface = artifact["common_core"]["surfaces"]["player_session"]
    assert core_surface["sample_counts"] == SAMPLE_COUNTS
    assert core_surface["scenarios"]["steady"]["render_ms"] == 0.0
    assert core_surface["pressure"]["active_payload_bytes_per_minute"] == 12000.0
    assert artifact["imported_phase7_evidence"] == IMPORTED_PHASE7_EVIDENCE


def test_real_raw_server_timing_shape_from_both_committed_harnesses_is_parsed_equivalently():
    phase4 = _phase4_measurement_module()
    current_path = Path("scripts/measure_live_latency.py")
    spec = importlib.util.spec_from_file_location("phase8_measure_live_latency_characterization", current_path)
    assert spec and spec.loader
    current = importlib.util.module_from_spec(spec)
    sys.modules[current.__name__] = current
    spec.loader.exec_module(current)
    raw = _sample(changed=False, request=12.0, db=1.25, render=0.0, apply=0.0, payload=84.0)

    phase4_normalized = phase4.normalize_sample(raw, scenario="steady", surface_name="session")
    current_normalized = current.normalize_sample(raw, scenario="steady", surface_name="session")

    assert "serverTimingParsed" not in raw
    assert phase4_normalized["serverTimingParsed"] == current_normalized["serverTimingParsed"] == {
        "state-check": 0.25,
        "db": 1.25,
        "render": 0.0,
        "total": 6.0,
    }
    assert parse_server_timing(raw["serverTiming"]) == phase4_normalized["serverTimingParsed"]
    artifact = build_candidate_artifact(_manifest("phase4"), _raw())
    assert artifact["common_core"]["surfaces"]["player_session"]["scenarios"]["steady"]["db_ms"] == 0.2


def test_collection_runner_executes_the_locked_two_actor_schedule_without_harness_changes():
    pages: list[_FakePage] = []

    def page_factory() -> _FakePage:
        page = _FakePage()
        pages.append(page)
        return page

    artifact = collect_candidate(
        _manifest("phase4"),
        base_url="http://127.0.0.1:5000",
        campaign="sanitized-campaign",
        credentials={"player": ("player@example.test", "player-password"), "manager": ("dm@example.test", "dm-password")},
        page_factory=page_factory,
    )

    assert len(pages) == len(SURFACES)
    assert artifact["common_core"]["surfaces"]["dm_session_tools"]["sample_counts"] == SAMPLE_COUNTS
    assert all(len(page.sampler_calls) == sum(SAMPLE_COUNTS.values()) for page in pages)
    assert all(page.waits == [100] * sum(SAMPLE_COUNTS.values()) for page in pages)
    assert all(call["forceApply"] is False for page in pages for call in page.sampler_calls[:21])
    assert all(call["forceApply"] is True for page in pages for call in page.sampler_calls[21:])
    assert pages[0].filled[0] == "player@example.test"
    assert pages[2].filled[0] == "dm@example.test"


def test_playwright_collection_uses_one_isolated_context_per_surface_and_closes_each(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    browser = _ContextBrowser()
    manager = _install_context_playwright(monkeypatch, browser)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest("phase8")), encoding="utf-8")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_PLAYER_EMAIL", "player@example.test")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_PLAYER_PASSWORD", "player-password")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_EMAIL", "dm@example.test")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_PASSWORD", "dm-password")

    artifact = _collect_with_playwright(
        types.SimpleNamespace(
            manifest=str(manifest_path),
            base_url="http://127.0.0.1:5000",
            campaign="sanitized-campaign",
        )
    )

    expected_emails = [
        "player@example.test",
        "player@example.test",
        "dm@example.test",
        "dm@example.test",
        "dm@example.test",
    ]
    assert len(browser.contexts) == len(SURFACES)
    assert [context.login_emails for context in browser.contexts] == [[email] for email in expected_emails]
    assert [context.cookies for context in browser.contexts] == [[f"session-for:{email}"] for email in expected_emails]
    assert len({id(context.cookies) for context in browser.contexts}) == len(SURFACES)
    assert all(len(context.pages) == 1 and context.pages[0].closed for context in browser.contexts)
    assert all(context.closed for context in browser.contexts)
    assert browser.closed is True
    assert manager.exited is True
    assert manager.playwright.chromium.launches == [True]
    assert all(len(context.pages[0].sampler_calls) == sum(SAMPLE_COUNTS.values()) for context in browser.contexts)
    assert artifact["manifest"] == _manifest("phase8")
    reports = artifact["common_core"]["surfaces"]
    assert list(reports) == [surface.name for surface in SURFACES]
    assert all(report["sample_counts"] == SAMPLE_COUNTS for report in reports.values())


def test_playwright_collection_closes_the_current_context_when_sign_in_redirect_remains_observable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    browser = _ContextBrowser(failed_context_index=2)
    manager = _install_context_playwright(monkeypatch, browser)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest("phase8")), encoding="utf-8")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_PLAYER_EMAIL", "player@example.test")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_PLAYER_PASSWORD", "player-password")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_EMAIL", "dm@example.test")
    monkeypatch.setenv("PLAYER_WIKI_MEASURE_PASSWORD", "dm-password")

    with pytest.raises(ContractError, match="dm_session_tools: sign-in did not complete for manager"):
        _collect_with_playwright(
            types.SimpleNamespace(
                manifest=str(manifest_path),
                base_url="http://127.0.0.1:5000",
                campaign="sanitized-campaign",
            )
        )

    assert [context.login_emails for context in browser.contexts] == [
        ["player@example.test"],
        ["player@example.test"],
        ["dm@example.test"],
    ]
    assert all(len(context.pages) == 1 and context.pages[0].closed for context in browser.contexts)
    assert all(context.closed for context in browser.contexts)
    assert browser.closed is True
    assert manager.exited is True


def test_phase8_retries_transient_non_object_sampler_results_and_preserves_raw_diagnostics():
    pages: list[_TransientPhase8SamplerPage] = []

    def page_factory() -> _TransientPhase8SamplerPage:
        page = _TransientPhase8SamplerPage()
        pages.append(page)
        return page

    artifact = collect_candidate(
        _manifest("phase8"),
        base_url="http://127.0.0.1:5000",
        campaign="sanitized-campaign",
        credentials={"player": ("player@example.test", "player-password"), "manager": ("dm@example.test", "dm-password")},
        page_factory=page_factory,
    )

    status_page = pages[3]
    status_raw = artifact["candidate_specific_raw"]["surfaces"]["dm_combat_status"]
    assert status_raw["errors"] == []
    assert {name: len(samples) for name, samples in status_raw["scenarios"].items()} == SAMPLE_COUNTS
    assert len(status_page.sampler_calls) == sum(SAMPLE_COUNTS.values()) + 2
    assert status_page.waits == [50, 50] + [100] * sum(SAMPLE_COUNTS.values())
    assert all(page.waits == [100] * sum(SAMPLE_COUNTS.values()) for page in pages[:3] + pages[4:])
    raw_sample = status_raw["scenarios"]["warmup"][0]
    assert "serverTiming" in raw_sample
    assert "serverTimingParsed" not in raw_sample
    assert parse_server_timing(raw_sample["serverTiming"])["db"] == 2.0
    assert artifact["common_core"]["surfaces"]["dm_combat_status"]["collection_complete"] is True


def test_phase8_sampler_retry_exhaustion_retains_one_failure_and_incomplete_hold_evidence(tmp_path):
    pages: list[_ExhaustedPhase8SamplerPage] = []

    def page_factory() -> _ExhaustedPhase8SamplerPage:
        page = _ExhaustedPhase8SamplerPage()
        pages.append(page)
        return page

    phase8 = collect_candidate(
        _manifest("phase8"),
        base_url="http://127.0.0.1:5000",
        campaign="sanitized-campaign",
        credentials={"player": ("player@example.test", "player-password"), "manager": ("dm@example.test", "dm-password")},
        page_factory=page_factory,
    )

    status_page = pages[3]
    status_raw = phase8["candidate_specific_raw"]["surfaces"]["dm_combat_status"]
    assert len(status_page.sampler_calls) == 50 + sum(SAMPLE_COUNTS.values()) - 1
    assert status_page.waits == [50] * 50 + [100] * (sum(SAMPLE_COUNTS.values()) - 1)
    assert {name: len(samples) for name, samples in status_raw["scenarios"].items()} == {
        "warmup": 0,
        "cold": 8,
        "steady": 12,
        "forced_apply": 6,
    }
    assert status_raw["errors"] == [
        {"kind": "sampler_exception", "message": "Sampler for combat did not return a sample for scenario warmup."},
        {
            "kind": "incomplete_schedule",
            "message": "dm_combat_status.warmup observed 0 samples; locked count is 1.",
        },
    ]
    result = evaluate_pair(_artifact("phase4"), phase8)
    assert result["accepted"] is False
    assert any("phase8 sample schedule differs" in hold for hold in result["holds"])
    assert any("phase8 unexpected sampler_exception" in hold for hold in result["holds"])
    hashes = write_deterministic_bundles(tmp_path, _artifact("phase4"), phase8)
    rendered = (tmp_path / "phase8.raw.json").read_text(encoding="utf-8")
    assert hashes["output_sha256"]["phase8.raw.json"]
    assert "Sampler for combat did not return a sample for scenario warmup." in rendered
    assert "password" not in rendered.lower()


def test_phase4_keeps_the_immediate_non_object_sampler_failure_policy():
    pages: list[_ExhaustedPhase8SamplerPage] = []

    def page_factory() -> _ExhaustedPhase8SamplerPage:
        page = _ExhaustedPhase8SamplerPage()
        pages.append(page)
        return page

    phase4 = collect_candidate(
        _manifest("phase4"),
        base_url="http://127.0.0.1:5000",
        campaign="sanitized-campaign",
        credentials={"player": ("player@example.test", "player-password"), "manager": ("dm@example.test", "dm-password")},
        page_factory=page_factory,
    )

    status_page = pages[3]
    status_raw = phase4["candidate_specific_raw"]["surfaces"]["dm_combat_status"]
    assert len(status_page.sampler_calls) == sum(SAMPLE_COUNTS.values())
    assert status_page.waits == [100] * (sum(SAMPLE_COUNTS.values()) - 1)
    assert 50 not in status_page.waits
    assert status_raw["errors"] == [
        {"kind": "sampler_exception", "message": "Sampler for combat did not return a sample for scenario warmup."},
        {
            "kind": "incomplete_schedule",
            "message": "dm_combat_status.warmup observed 0 samples; locked count is 1.",
        },
    ]
    assert status_raw["scenarios"]["warmup"] == []


def test_dm_combat_status_no_ticket_is_retained_as_incomplete_raw_evidence_without_metric_substitution():
    pages: list[_DmStatusNoTicketPage] = []

    def page_factory() -> _DmStatusNoTicketPage:
        page = _DmStatusNoTicketPage()
        pages.append(page)
        return page

    artifact = collect_candidate(
        _manifest("phase8"),
        base_url="http://127.0.0.1:5000",
        campaign="sanitized-campaign",
        credentials={"player": ("player@example.test", "player-password"), "manager": ("dm@example.test", "dm-password")},
        page_factory=page_factory,
    )

    status_raw = artifact["candidate_specific_raw"]["surfaces"]["dm_combat_status"]
    assert status_raw["scenarios"]["warmup"] == []
    assert sum(len(status_raw["scenarios"][scenario]) for scenario in ("cold", "steady", "forced_apply")) == 26
    assert status_raw["errors"] == [
        {"kind": "sampler_exception", "message": "async read has no ticket at <path> <redacted>"},
        {
            "kind": "incomplete_schedule",
            "message": "dm_combat_status.warmup observed 0 samples; locked count is 1.",
        },
    ]
    status_core = artifact["common_core"]["surfaces"]["dm_combat_status"]
    assert status_core["collection_complete"] is False
    assert status_core["sample_counts"] == {"warmup": 0, "cold": 8, "steady": 12, "forced_apply": 6}
    assert "scenarios" not in status_core
    assert "pressure" not in status_core
    assert len(pages) == len(SURFACES)

    result = evaluate_pair(_artifact("phase4"), artifact)

    assert result["accepted"] is False
    assert any("phase8 sample schedule differs" in hold for hold in result["holds"])
    assert any("phase8 unexpected sampler_exception: async read has no ticket" in hold for hold in result["holds"])
    assert not any(hold.startswith("dm_combat_status.cold.") for hold in result["holds"])
    assert not any(hold.startswith("dm_combat_status.steady.") for hold in result["holds"])
    assert not any(hold.startswith("dm_combat_status.forced_apply.") for hold in result["holds"])

    status_surface = next(surface for surface in SURFACES if surface.name == "dm_combat_status")
    assert status_surface.root_selector == "[data-combat-live-root]"
    assert status_surface.metric_view == "combat"
    phase8_combat_source = subprocess.run(
        ["git", "show", "3fdb48c9bed822719a2c71c8463c7e52474cdd2d:player_wiki/static/combat-live.js"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert 'if (asyncPolicy && !readTicket) {' in phase8_combat_source
    assert 'diagnosticsTools.registerSampler("combat", async (options = {}) => {' in phase8_combat_source


def test_incomplete_schedule_writes_a_deterministic_credential_and_path_free_hold_bundle(tmp_path):
    phase4 = _artifact("phase4")
    phase8 = build_candidate_artifact(_manifest("phase8"), _incomplete_phase8_raw())

    hashes = write_deterministic_bundles(tmp_path, phase4, phase8)
    first = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}
    second_hashes = write_deterministic_bundles(tmp_path, phase4, phase8)
    second = {path.name: path.read_bytes() for path in sorted(tmp_path.iterdir())}

    assert hashes == second_hashes
    assert first == second
    assert sorted(first) == [
        "comparison.json",
        "comparison.md",
        "phase4.raw.json",
        "phase4.raw.md",
        "phase8.raw.json",
        "phase8.raw.md",
    ]
    assert set(hashes["output_sha256"]) == set(first)
    comparison = json.loads(first["comparison.json"])
    assert comparison["comparison"]["accepted"] is False
    assert any("metric comparisons are not evaluated" in hold for hold in comparison["comparison"]["holds"])
    rendered = b"".join(first.values()).decode("utf-8")
    assert "C:\\" not in rendered
    assert "password" not in rendered.lower()
    assert "credential" not in rendered.lower()

    phase4_path = tmp_path / "phase4.json"
    phase8_path = tmp_path / "phase8.json"
    cli_output = tmp_path / "cli-hold-bundle"
    phase4_path.write_text(json.dumps(phase4), encoding="utf-8")
    phase8_path.write_text(json.dumps(phase8), encoding="utf-8")
    assert main([
        "bundle",
        "--phase4",
        str(phase4_path),
        "--phase8",
        str(phase8_path),
        "--output-dir",
        str(cli_output),
    ]) == 2
    assert sorted(path.name for path in cli_output.iterdir()) == sorted(first)


def test_missing_or_unassigned_combat_character_is_a_hold_not_a_pass():
    manifest = _manifest("phase4")
    manifest["combat_character"] = {"slug": "", "assigned": False}

    with pytest.raises(ContractError, match="combat_character"):
        build_candidate_artifact(manifest, _raw())


def test_adapter_retains_ad_hoc_sample_schema_failure_as_a_structured_hold():
    raw = _raw()
    sample = raw["surfaces"]["player_session"]["scenarios"]["cold"][0]
    sample["request_ms"] = sample.pop("requestMs")

    artifact = build_candidate_artifact(_manifest("phase4"), raw)

    surface = artifact["common_core"]["surfaces"]["player_session"]
    assert surface["collection_complete"] is False
    assert "scenarios" not in surface
    assert surface["errors"] == [{"kind": "schema_error", "message": "requestMs must be numeric."}]
    result = evaluate_pair(artifact, _artifact("phase8"))
    assert result["accepted"] is False
    assert any("phase4 unexpected schema_error: requestMs must be numeric" in hold for hold in result["holds"])


def test_adapter_retains_preinjected_server_timing_schema_failure_as_a_structured_hold():
    raw = _raw()
    sample = raw["surfaces"]["player_session"]["scenarios"]["cold"][0]
    sample.pop("serverTiming")
    sample["serverTimingParsed"] = {"db": 2.0, "render": 1.0}

    artifact = build_candidate_artifact(_manifest("phase4"), raw)

    surface = artifact["common_core"]["surfaces"]["player_session"]
    assert surface["collection_complete"] is False
    assert "scenarios" not in surface
    assert surface["errors"] == [
        {"kind": "schema_error", "message": "sample.serverTiming must be the raw source-proven browser diagnostic string."}
    ]
    result = evaluate_pair(artifact, _artifact("phase8"))
    assert result["accepted"] is False
    assert any("phase4 unexpected schema_error: sample.serverTiming" in hold for hold in result["holds"])


def test_adapter_rejects_schema_or_fixture_drift_before_comparison():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["manifest"]["fixture_sha256"] = "e" * 64

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is False
    assert result["holds"] == ["manifest.fixture_sha256 does not match the raw pinned sanitized fixture manifest."]


def test_adapter_accepts_locked_schedule_zero_semantics_and_controls_within_threshold():
    phase4 = _artifact("phase4")
    for surface in phase4["common_core"]["surfaces"].values():
        surface.pop("collection_complete")

    result = evaluate_pair(phase4, _artifact("phase8"))

    assert result["accepted"] is True
    assert all(surface["accepted"] is True for surface in result["surface_results"].values())


def test_adapter_rejects_more_than_fifteen_percent_p95_regression():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["player_combat"]["scenarios"]["cold"]["request_ms"] = 11.6

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is False
    assert any("player_combat.cold.request_ms p95 regression" in hold for hold in result["holds"])


def test_adapter_rejects_nonzero_semantic_zero_render_and_unexpected_errors():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["player_session"]["scenarios"]["steady"]["render_ms"] = 0.1
    phase8["common_core"]["surfaces"]["dm_session_tools"]["errors"] = [
        {"kind": "console_error", "message": "unexpected console failure"}
    ]

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is False
    assert any("semantic zero" in hold for hold in result["holds"])
    assert any("unexpected console_error" in hold for hold in result["holds"])


def test_predeclared_console_allowlist_does_not_count_as_an_unexpected_error():
    phase4 = _artifact("phase4")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["dm_combat_status"]["errors"] = [
        {"kind": "console_error", "message": "known diagnostics noise"}
    ]

    result = evaluate_pair(phase4, phase8)

    assert result["accepted"] is True


def test_compare_cli_writes_hold_result_without_normalizing_artifacts(tmp_path):
    phase4_path = tmp_path / "phase4.json"
    phase8_path = tmp_path / "phase8.json"
    output_path = tmp_path / "result.json"
    phase4_path.write_text(json.dumps(_artifact("phase4")), encoding="utf-8")
    phase8 = _artifact("phase8")
    phase8["common_core"]["surfaces"]["player_session"]["sample_counts"] = {"warmup": 0}
    phase8_path.write_text(json.dumps(phase8), encoding="utf-8")

    exit_code = main([
        "compare",
        "--phase4",
        str(phase4_path),
        "--phase8",
        str(phase8_path),
        "--output",
        str(output_path),
    ])

    assert exit_code == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["accepted"] is False
    assert any("sample schedule" in hold for hold in payload["holds"])
