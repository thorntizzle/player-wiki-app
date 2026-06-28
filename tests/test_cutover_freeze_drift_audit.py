from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_audit_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "cutover_freeze_drift_audit.py"
    spec = importlib.util.spec_from_file_location("cutover_freeze_drift_audit", module_path)
    assert spec and spec.loader is not None, f"Unable to load {module_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, repo_root


def test_cutover_freeze_drift_inputs_are_present_and_parseable():
    audit_module, repo_root = _load_audit_module()

    result = audit_module.run_audit(repo_root)

    assert result.failures == []


def test_cutover_freeze_drift_audit_reports_missing_required_inputs(tmp_path):
    audit_module, _repo_root = _load_audit_module()

    result = audit_module.run_audit(tmp_path)

    assert result.failures
    assert any("missing required file" in failure for failure in result.failures)
