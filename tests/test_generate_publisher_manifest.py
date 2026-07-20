from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "generate_publisher_manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_publisher_manifest", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
publisher_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher_manifest)


def _nodeids_cache(tmp_path: Path, nodeids: list[str]) -> Path:
    path = tmp_path / "nodeids"
    path.write_text(json.dumps(nodeids), encoding="utf-8")
    return path


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_manifest_expands_parameterized_selectors_and_binds_candidate(tmp_path):
    cache = _nodeids_cache(
        tmp_path,
        [
            "tests/test_route_contract_manifest.py::test_example[desktop]",
            "tests/test_route_contract_manifest.py::test_example[mobile]",
            "tests/test_route_contract_manifest.py::test_unrelated",
        ],
    )

    manifest = publisher_manifest.build_publisher_manifest(
        project_root=PROJECT_ROOT,
        accepted_commit=_head_commit(),
        nodeids_cache=cache,
        selectors=["tests/test_route_contract_manifest.py::test_example"],
        live_routes=["home:GET"],
    )

    assert len(manifest["accepted_candidate"]["commit"]) == 40
    assert len(manifest["accepted_candidate"]["tree"]) == 40
    assert manifest["tests"]["expanded_nodeids"] == [
        "tests/test_route_contract_manifest.py::test_example[desktop]",
        "tests/test_route_contract_manifest.py::test_example[mobile]",
    ]
    cache_label = manifest["tests"]["nodeids_cache"]["path"]
    assert cache_label.endswith("/nodeids")
    assert not Path(cache_label).is_absolute()
    assertion = manifest["live_routes"]["assertions"][0]
    assert assertion["endpoint"] == "home"
    assert assertion["method"] == "GET"
    assert assertion["route"] == "/"
    assert assertion["authentication_policy"] == "optional_identity"


def test_manifest_bytes_are_deterministic_and_do_not_embed_absolute_cache_path(tmp_path):
    cache = _nodeids_cache(
        tmp_path,
        ["tests/test_route_contract_manifest.py::test_one"],
    )
    manifest = publisher_manifest.build_publisher_manifest(
        project_root=PROJECT_ROOT,
        accepted_commit=_head_commit(),
        nodeids_cache=cache,
        selectors=["tests/test_route_contract_manifest.py::test_one"],
    )

    first = publisher_manifest.manifest_bytes(manifest)
    second = publisher_manifest.manifest_bytes(manifest)

    assert first == second
    assert str(tmp_path).encode() not in first
    assert first.endswith(b"\n")


def test_manifest_rejects_stale_selector(tmp_path):
    cache = _nodeids_cache(
        tmp_path,
        ["tests/test_route_contract_manifest.py::test_one"],
    )

    with pytest.raises(
        publisher_manifest.PublisherManifestError,
        match="matched no retained node IDs",
    ):
        publisher_manifest.build_publisher_manifest(
            project_root=PROJECT_ROOT,
            accepted_commit=_head_commit(),
            nodeids_cache=cache,
            selectors=["tests/test_route_contract_manifest.py::test_missing"],
        )


def test_manifest_rejects_mutating_live_route(tmp_path):
    cache = _nodeids_cache(
        tmp_path,
        ["tests/test_route_contract_manifest.py::test_one"],
    )

    with pytest.raises(
        publisher_manifest.PublisherManifestError,
        match="read-only GET routes",
    ):
        publisher_manifest.build_publisher_manifest(
            project_root=PROJECT_ROOT,
            accepted_commit=_head_commit(),
            nodeids_cache=cache,
            selectors=["tests/test_route_contract_manifest.py::test_one"],
            live_routes=["account_session_chat_order_update:POST"],
        )


def test_manifest_requires_full_accepted_sha(tmp_path):
    cache = _nodeids_cache(
        tmp_path,
        ["tests/test_route_contract_manifest.py::test_one"],
    )

    with pytest.raises(
        publisher_manifest.PublisherManifestError,
        match="full 40-character",
    ):
        publisher_manifest.build_publisher_manifest(
            project_root=PROJECT_ROOT,
            accepted_commit="HEAD",
            nodeids_cache=cache,
            selectors=["tests/test_route_contract_manifest.py::test_one"],
        )


def test_manifest_output_is_confined_to_ignored_evidence_root():
    with pytest.raises(
        publisher_manifest.PublisherManifestError,
        match="inside the repository .local",
    ):
        publisher_manifest._output_path(PROJECT_ROOT / "manifest.json", PROJECT_ROOT)


def test_local_wrapper_generates_manifest_without_cwd_artifacts(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    cache = _nodeids_cache(
        evidence,
        ["tests/test_route_contract_manifest.py::test_wrapper_case[one]"],
    )
    output = evidence / "publisher-manifest.json"
    invocation_cwd = tmp_path / "invocation"
    invocation_cwd.mkdir()

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "local.ps1"),
            "-Action",
            "publisher-manifest",
            "-PythonPath",
            sys.executable,
            "-PublisherAcceptedCommit",
            _head_commit(),
            "-PublisherNodeidsCache",
            cache.relative_to(PROJECT_ROOT).as_posix(),
            "-PublisherTestSelector",
            "tests/test_route_contract_manifest.py::test_wrapper_case",
            "-PublisherLiveRoute",
            "home:GET",
            "-PublisherManifestOutput",
            output.relative_to(PROJECT_ROOT).as_posix(),
        ],
        cwd=invocation_cwd,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["tests"][
        "expanded_nodeid_count"
    ] == 1
    assert list(invocation_cwd.iterdir()) == []
