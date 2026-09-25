from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from scripts.select_release_risk_tests import select


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _fixture(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "risk"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Risk Test")
    (root / "tests").mkdir()
    for name in ("baseline", "auth", "windows"):
        (root / "tests" / f"test_{name}.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (root / "player_wiki").mkdir()
    (root / "player_wiki" / "auth_store.py").write_text("BASE = True\n", encoding="utf-8")
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "baseline_linux": ["tests/test_baseline.py"],
        "baseline_windows": ["tests/test_windows.py"],
        "domains": {"auth": ["tests/test_auth.py"]},
        "source_rules": [
            {"pattern": "^player_wiki/auth", "domains": ["auth"]},
            {"pattern": "^tests/conftest\\.py$", "domains": ["auth"]},
        ],
    }), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD"), manifest


def _shipped_fixture(tmp_path: Path) -> tuple[Path, str, Path]:
    source = Path(__file__).resolve().parents[1] / "validation/release-risk-manifest.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    root = tmp_path / "shipped-risk"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Risk Test")
    selectors = [*manifest["baseline_linux"], *manifest["baseline_windows"]]
    selectors += [item for domain in manifest["domains"].values() for item in domain]
    for selector in selectors:
        target = root / selector.split("::", 1)[0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def test_ok(): pass\n", encoding="utf-8")
    reviewed = root / "player_wiki/auth.py"
    reviewed.parent.mkdir(parents=True)
    reviewed.write_text("BASE = True\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD"), source


def _source_domains(manifest: dict, path: str) -> list[str]:
    return sorted({domain for rule in manifest["source_rules"]
                   if re.search(rule["pattern"], path) for domain in rule["domains"]})


def test_changed_source_adds_affected_domain(tmp_path):
    root, base, manifest = _fixture(tmp_path)
    (root / "player_wiki" / "auth_store.py").write_text("BASE = False\n", encoding="utf-8")
    plan = select(root, base, manifest)
    assert plan["domains"] == ["auth"]
    assert plan["linux"] == ["tests/test_auth.py", "tests/test_baseline.py"]
    assert plan["windows"] == ["tests/test_windows.py"]


def test_changed_source_bytes_are_bound_to_selection(tmp_path):
    root, base, manifest = _fixture(tmp_path)
    source = root / "player_wiki" / "auth_store.py"
    source.write_text("BASE = False\n", encoding="utf-8")
    first = select(root, base, manifest)
    source.write_text("BASE = None\n", encoding="utf-8")
    second = select(root, base, manifest)
    assert first["changed_paths"] == second["changed_paths"]
    assert first["domains"] == second["domains"]
    assert first["changed_bytes"] != second["changed_bytes"]


def test_unknown_candidate_source_fails_closed(tmp_path):
    root, base, manifest = _fixture(tmp_path)
    (root / "player_wiki" / "new_surface.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unmapped candidate paths"):
        select(root, base, manifest)


def test_shipped_manifest_rejects_unreviewed_auth_until_exact_rule_is_added(tmp_path):
    root, base, manifest_path = _shipped_fixture(tmp_path)
    (root / "player_wiki/auth_unreviewed.py").write_text("VALUE = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unmapped candidate paths.*auth_unreviewed.py"):
        select(root, base, manifest_path)

    reviewed = json.loads(manifest_path.read_text(encoding="utf-8"))
    reviewed["source_rules"].append({
        "pattern": "^player_wiki/auth_unreviewed\\.py$", "domains": ["auth"]
    })
    reviewed_path = tmp_path / "reviewed-manifest.json"
    reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
    plan = select(root, base, reviewed_path)
    assert plan["domains"] == ["auth"]
    assert "tests/test_auth_and_wiki.py" in plan["linux"]


def test_shipped_manifest_selects_changed_reviewed_auth_module(tmp_path):
    root, base, manifest_path = _shipped_fixture(tmp_path)
    (root / "player_wiki/auth.py").write_text("BASE = False\n", encoding="utf-8")
    plan = select(root, base, manifest_path)
    assert plan["domains"] == ["auth"]
    assert "tests/test_auth_and_wiki.py" in plan["linux"]


def test_new_test_is_added_and_windows_marker_routes_to_host(tmp_path):
    root, base, manifest = _fixture(tmp_path)
    (root / "tests" / "test_new.py").write_text(
        "import pytest\n@pytest.mark.windows_host\ndef test_new(): pass\n", encoding="utf-8"
    )
    plan = select(root, base, manifest)
    assert "tests/test_new.py" in plan["linux"]
    assert "tests/test_new.py" in plan["windows"]


def test_reviewed_shared_fixture_rule_selects_affected_domains(tmp_path):
    root, base, manifest = _fixture(tmp_path)
    (root / "tests" / "conftest.py").write_text("FIXTURE = True\n", encoding="utf-8")
    plan = select(root, base, manifest)
    assert plan["domains"] == ["auth"]
    assert plan["linux"] == ["tests/test_auth.py", "tests/test_baseline.py"]


@pytest.mark.parametrize("path", ["tests/helper.py", "tests/test_nested/helper.py"])
def test_unreviewed_test_helper_fails_closed(tmp_path, path):
    root, base, manifest = _fixture(tmp_path)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unmapped candidate paths"):
        select(root, base, manifest)


def test_shipped_manifest_covers_current_player_wiki_inventory_only():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "validation/release-risk-manifest.json").read_text(encoding="utf-8"))
    paths = _git(root, "ls-files", "player_wiki").splitlines()
    assert paths
    assert all(any(re.search(rule["pattern"], path) for rule in manifest["source_rules"])
               for path in paths)
    assert not any(re.search(rule["pattern"], "player_wiki/new_unreviewed_module.py")
                   for rule in manifest["source_rules"])
    assert not any(rule["pattern"] == "^player_wiki/" for rule in manifest["source_rules"])


def test_shipped_manifest_preserves_r1_domains_and_rejects_python_neighbors():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "validation/release-risk-manifest.json").read_text(encoding="utf-8"))
    paths = _git(root, "ls-files", "player_wiki").splitlines()
    assert len(paths) == 376
    domains = {path: _source_domains(manifest, path) for path in paths}
    assert all(domains.values())
    # Frozen R1-A1 mapping over every tracked app path, including overlaps.
    canonical = json.dumps(domains, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == (
        "66c3dec365048e92ad4b3ee2f331252842ffedf6073b1d75f64564ec3b3f42ba"
    )
    assert domains["player_wiki/runtime_lease.py"] == ["auth", "core", "recovery"]
    python_paths = [path for path in paths if path.endswith(".py")]
    assert len(python_paths) == 233
    for path in python_paths:
        neighbor = path[:-3] + "_unreviewed.py"
        assert not _source_domains(manifest, neighbor), neighbor
    for path in ("player_wiki/static/new_unreviewed.py",
                 "player_wiki/templates/new_unreviewed.py"):
        assert not _source_domains(manifest, path), path


def test_shipped_shared_fixture_rule_selects_every_domain():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "validation/release-risk-manifest.json").read_text(encoding="utf-8"))
    fixture_rules = [rule for rule in manifest["source_rules"]
                     if re.search(rule["pattern"], "tests/conftest.py")]
    assert len(fixture_rules) == 1
    assert set(fixture_rules[0]["domains"]) == set(manifest["domains"])


def test_invalid_base_is_refused(tmp_path):
    root, _, manifest = _fixture(tmp_path)
    with pytest.raises(ValueError, match="full lowercase"):
        select(root, "HEAD", manifest)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("baseline_linux", [], "nonempty selector list"),
    ("baseline_windows", "tests/test_windows.py", "nonempty selector list"),
    ("baseline_linux", ["../tests/test_baseline.py"], "unsafe test selector"),
    ("baseline_linux", ["/tmp/test_baseline.py"], "must name a test file"),
    ("baseline_linux", ["tests/../tests/test_baseline.py"], "unsafe test selector"),
    ("baseline_linux", ["tests/test_baseline.py::../test_bad"], "unsafe test selector"),
    ("baseline_linux", ["player_wiki/app.py"], "must name a test file"),
    ("domains", {}, "nonempty mapping"),
    ("domains", {"auth": "tests/test_auth.py"}, "nonempty selector list"),
    ("source_rules", [], "nonempty list"),
    ("source_rules", [{"pattern": "[", "domains": ["auth"]}], "anchored pattern"),
    ("source_rules", [{"pattern": "^[", "domains": ["auth"]}], "invalid pattern"),
    ("source_rules", ["^player_wiki/auth"], "pattern and domains"),
    ("source_rules", [{"pattern": "^player_wiki/auth", "domains": ["missing"]}], "invalid domains"),
])
def test_invalid_manifest_fails_closed(tmp_path, field, value, message):
    root, base, manifest = _fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload[field] = value
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        select(root, base, manifest)


def test_missing_manifest_structure_fails_closed(tmp_path):
    root, base, manifest = _fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    del payload["source_rules"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="missing or unexpected fields"):
        select(root, base, manifest)


def test_shipped_manifest_keeps_required_release_boundaries():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "validation/release-risk-manifest.json").read_text(encoding="utf-8"))
    linux = set(manifest["baseline_linux"])
    windows = set(manifest["baseline_windows"])
    assert {"tests/test_auth_and_wiki.py", "tests/test_api_admin_account.py",
            "tests/test_contract_smoke.py",
            "tests/test_csrf.py",
            "tests/test_rich_text_security.py", "tests/test_migrations.py",
            "tests/test_backup_archive.py", "tests/test_restore_transaction.py",
            "tests/test_player_wiki_reconciliation.py"} <= linux
    assert "tests/test_file_publication.py" in windows
    assert "tests/test_runtime_lease.py" in windows
    assert any("browser.py::" in item for item in linux)
    for item in linux | windows:
        assert (root / item.split("::", 1)[0]).is_file()
